import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtempSync,rmSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as sleep} from 'node:timers/promises';

const root=dirname(fileURLToPath(import.meta.url));
const temp=mkdtempSync(join(root,'.integrated-'));
const port=19322,origin='http://127.0.0.1:7863';
const chrome=spawn('chromium',[
 '--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-gpu',
 '--remote-allow-origins=*','--remote-debugging-port='+port,
 '--user-data-dir='+join(temp,'profile'),'--window-size=1000,800',origin+'/'
],{stdio:'ignore'});
const pending=new Map();let ws,seq=0;
const issues=[];
async function endpoint(){
 for(let i=0;i<100;i++){
  try{
   const targets=await (await fetch('http://127.0.0.1:'+port+'/json')).json();
   const target=targets.find(t=>t.type==='page'&&t.url.startsWith(origin));
   if(target)return target.webSocketDebuggerUrl;
  }catch{}
  await sleep(75);
 }
 throw Error('Browser did not start');
}
function cmd(method,params={}){
 const id=++seq;return new Promise((resolve,reject)=>{
  pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));
 });
}
async function evaluate(expression){
 const x=await cmd('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
 if(x.result.exceptionDetails)throw Error(JSON.stringify(x.result.exceptionDetails));
 return x.result.result.value;
}
async function waitFor(expr,msg){
 for(let i=0;i<120;i++){
  try{if(await evaluate(expr))return;}catch{}
  await sleep(80);
 }
 throw Error('Timed out: '+msg);
}
async function mouse(type,p,buttons=0){
 await cmd('Input.dispatchMouseEvent',{type,x:p.x,y:p.y,button:'left',buttons,clickCount:1});
}
async function click(p){await mouse('mousePressed',p,1);await mouse('mouseReleased',p);}
const elPoint=sel=>evaluate("(()=>{const r=document.querySelector("+JSON.stringify(sel)+").getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()");
const childPoint=sel=>evaluate("(()=>{const f=document.querySelector('#sketch-frame'),r=f.getBoundingClientRect(),e=f.contentDocument.querySelector("+JSON.stringify(sel)+").getBoundingClientRect();return {x:r.left+e.left+e.width/2,y:r.top+e.top+e.height/2}})()");
const storage=()=>evaluate("JSON.parse(sessionStorage.getItem('popai.composer-session')).references");
const refCount=()=>evaluate("document.querySelector('#reference-preview').children.length");
const sketchOpen=()=>waitFor("document.querySelector('#sketch-dialog').open && document.querySelector('#sketch-frame').contentDocument?.querySelector('#canvas')",'editor opens');
const canvasInk=()=>evaluate("(()=>{const d=document.querySelector('#sketch-frame').contentDocument.querySelector('#canvas').getContext('2d').getImageData(0,0,960,720).data;let n=0;for(let i=3;i<d.length;i+=4)if(d[i])n++;return n})()");
async function sketchStroke(dx=0,dy=0){
 const c=await childPoint('#canvas');
 await mouse('mousePressed',{x:c.x-70+dx,y:c.y-35+dy},1);
 await mouse('mouseMoved',{x:c.x+25+dx,y:c.y+45+dy},1);
 await mouse('mouseReleased',{x:c.x+25+dx,y:c.y+45+dy});
}
async function saved(){
 await click(await childPoint('#confirm'));
 await waitFor("!document.querySelector('#sketch-dialog').open && document.querySelector('#reference-preview').children.length >= 1",'sketch saved');
 await waitFor("document.querySelector('#reference-preview .reference-open[data-sketch]')",'sketch thumbnail');
}
async function reload(){
 await cmd('Page.reload',{ignoreCache:true});
 await sleep(400);
 await waitFor("document.querySelector('#reference-preview') && document.querySelector('#draw-reference')",'reload complete');
}
try{
 const url=await endpoint();ws=new WebSocket(url);
 await new Promise((yes,no)=>{ws.onopen=yes;ws.onerror=no;});
 ws.onmessage=e=>{
  const event=JSON.parse(e.data);
  if(event.method==='Runtime.exceptionThrown')issues.push(event.params.exceptionDetails.text);
  if(event.method==='Log.entryAdded'&&event.params.entry.level==='error')issues.push(event.params.entry.text);
  const p=pending.get(event.id);
  if(p){pending.delete(event.id);event.error?p.reject(Error(JSON.stringify(event.error))):p.resolve(event);}
 };
 await cmd('Runtime.enable');await cmd('Page.enable');await cmd('Log.enable');
 await waitFor("document.querySelector('#draw-reference') && !document.querySelector('#draw-reference').hidden",'Klein button visible');
 const pos=await evaluate("(()=>{const a=document.querySelector('#add-reference').getBoundingClientRect(),b=document.querySelector('#draw-reference').getBoundingClientRect();return {plusRight:a.right,penLeft:b.left}})()");
 assert.ok(pos.penLeft>=pos.plusRight-2 && pos.penLeft<=pos.plusRight+12,'Pen is immediately right of +');

 // New drawing: save an editable vector state plus its PNG.
 await click(await elPoint('#draw-reference'));
 await sketchOpen();
 assert.equal(await evaluate("document.querySelector('#sketch-frame').contentDocument.documentElement.classList.contains('embedded')"),true);
 await sketchStroke();
 await saved();
 assert.equal(await refCount(),1);
 let refs=await storage();
 assert.equal(refs[0].sketch.items.length,1,'Saved sketch keeps its editable stroke');
 const originalId=refs[0].id;
 assert.equal(await evaluate("document.querySelector('#reference-preview img').naturalWidth>0"),true);

 // Reopen that exact drawing by clicking the thumbnail and edit it.
 await click(await elPoint('#reference-preview .reference-open'));
 await sketchOpen();
 await waitFor("(document.querySelector('#sketch-frame').contentDocument.querySelector('#canvas').getContext('2d').getImageData(0,0,960,720).data.some(n=>n>0))",'vector restored');
 const oldInk=await canvasInk();
 assert.ok(oldInk>300,'Original stroke is restored');
 await sketchStroke(100,70);
 await saved();
 refs=await storage();
 assert.equal(refs.length,1,'Editing replaces the reference rather than appending');
 assert.notEqual(refs[0].id,originalId,'Updated sketch gets fresh backend image ID');
 assert.equal(refs[0].sketch.items.length,2,'The original and the new strokes remain editable');

 // Reload the main page; the layers should survive in sessionStorage.
 await reload();
 await waitFor("document.querySelector('#reference-preview').children.length===1",'reference restored after reload');
 refs=await storage();
 assert.equal(refs[0].sketch.items.length,2,'Reload kept the editable data');
 await click(await elPoint('#reference-preview .reference-open'));
 await sketchOpen();
 await waitFor("document.querySelector('#sketch-frame').contentDocument.querySelector('#canvas').getContext('2d').getImageData(0,0,960,720).data.some(n=>n>0)",'editable picture restored after reload');
 await click(await childPoint('#close'));
 await waitFor("!document.querySelector('#sketch-dialog').open",'editor closed');

 // Legacy drawings: reopen as a flattened raster base and edit on top.
 await evaluate("(()=>{let s=JSON.parse(sessionStorage.getItem('popai.composer-session'));delete s.references[0].sketch;sessionStorage.setItem('popai.composer-session',JSON.stringify(s))})()");
 await reload();
 await waitFor("document.querySelector('#reference-preview').children.length===1",'legacy reference restored');
 await click(await elPoint('#reference-preview .reference-open'));
 await sketchOpen();
 await waitFor("document.querySelector('#sketch-frame').contentDocument.querySelector('#canvas').getContext('2d').getImageData(0,0,960,720).data.some(n=>n>0)",'legacy PNG loaded as background');
 await sketchStroke(110,-90);
 await saved();
 refs=await storage();
 assert.equal(refs.length,1,'Legacy sketch replaces original');
 assert.ok(refs[0].sketch.base?.startsWith('data:image/png;base64,'),'Legacy PNG persists as flattened background');
 assert.equal(refs[0].sketch.items.length,1,'Added stroke remains individually editable');

 // Ordinary uploaded image: click to enlarge, close without changing references.
 const countBefore=await refCount();
 await evaluate("(async()=>{const img=document.querySelector('#reference-preview img').src;const blob=await (await fetch(img)).blob();const transfer=new DataTransfer();transfer.items.add(new File([blob],'ordinary.png',{type:'image/png'}));const input=document.querySelector('#reference-file');input.files=transfer.files;input.dispatchEvent(new Event('change',{bubbles:true}));})()");
 await waitFor("document.querySelector('#reference-preview').children.length===2",'ordinary file uploaded');
 assert.equal(await refCount(),countBefore+1);
 await click(await elPoint('#reference-preview .reference-item:nth-child(2) .reference-open'));
 await waitFor("document.querySelector('#reference-dialog').open",'large image preview opened');
 const enlarged=await evaluate("(()=>{const r=document.querySelector('#reference-large').getBoundingClientRect();return {w:r.width,h:r.height,alt:document.querySelector('#reference-large').alt}})()");
 assert.equal(enlarged.alt,'ordinary.png');
 assert.ok(enlarged.w>72&&enlarged.h>56,'Preview is larger than thumbnail');
 await click(await elPoint('#reference-close'));
 assert.equal(await evaluate("document.querySelector('#reference-dialog').open"),false);
 assert.equal(await refCount(),2);

 // Both new shapes are independent items with selection, resizing and undo/redo.
 await click(await elPoint('#reference-preview .reference-item:nth-child(1) .reference-open'));
 await sketchOpen();
 await click(await childPoint('[data-tool="shape"]'));
 await waitFor("!document.querySelector('#sketch-frame').contentDocument.querySelector('#shapes').hidden",'shapes popup');
 assert.equal(await evaluate("document.querySelector('#sketch-frame').contentDocument.querySelectorAll('[data-shape]').length"),4);
 await click(await childPoint('[data-shape="line"]'));
 const center=await childPoint('#canvas');
 const lineStart={x:center.x-120,y:center.y-100},lineEnd={x:center.x+70,y:center.y-100};
 await mouse('mousePressed',lineStart,1);
 await mouse('mouseMoved',lineEnd,1);
 await mouse('mouseReleased',lineEnd);
 await click(await childPoint('[data-tool="shape"]'));
 await click(await childPoint('[data-shape="arrow"]'));
 const arrowStart={x:center.x-120,y:center.y+110},arrowEnd={x:center.x+75,y:center.y+110};
 await mouse('mousePressed',arrowStart,1);
 await mouse('mouseMoved',arrowEnd,1);
 await mouse('mouseReleased',arrowEnd);
 await click(await childPoint('[data-tool="move"]'));
 await mouse('mousePressed',{x:center.x-40,y:center.y-100},1);
 assert.equal(await evaluate("document.querySelector('#sketch-frame').contentDocument.querySelector('#selection-box').dataset.index"),'1','Straight line individually selectable');
 await mouse('mouseReleased',{x:center.x-40,y:center.y-100});
 const lineBefore=await evaluate("document.querySelector('#sketch-frame').contentDocument.querySelector('#canvas').toDataURL()");
 const handle=await childPoint('.resize-handle[data-corner="se"]');
 await mouse('mousePressed',handle,1);
 await mouse('mouseMoved',{x:handle.x+24,y:handle.y+20},1);
 await mouse('mouseReleased',{x:handle.x+24,y:handle.y+20});
 const lineAfter=await evaluate("document.querySelector('#sketch-frame').contentDocument.querySelector('#canvas').toDataURL()");
 assert.notEqual(lineAfter,lineBefore,'The line can be resized');
 await click(await childPoint('#undo'));
 assert.equal(await evaluate("document.querySelector('#sketch-frame').contentDocument.querySelector('#canvas').toDataURL()"),lineBefore,'Undo line resize');
 await click(await childPoint('#redo'));
 assert.equal(await evaluate("document.querySelector('#sketch-frame').contentDocument.querySelector('#canvas').toDataURL()"),lineAfter,'Redo line resize');
 await mouse('mousePressed',{x:center.x-20,y:center.y+110},1);
 assert.equal(await evaluate("document.querySelector('#sketch-frame').contentDocument.querySelector('#selection-box').dataset.index"),'2','Arrow individually selectable');
 await mouse('mouseMoved',{x:center.x+4,y:center.y+128},1);
 await mouse('mouseReleased',{x:center.x+4,y:center.y+128});
 await saved();
 refs=await storage();
 assert.deepEqual(refs[0].sketch.items.map(item=>item.kind),['pen','line','arrow'],'Both shapes are stored as editable objects');
 await reload();
 await waitFor("document.querySelector('#reference-preview').children.length===2",'shapes persist after reload');
 await click(await elPoint('#reference-preview .reference-item:nth-child(1) .reference-open'));
 await sketchOpen();
 await waitFor("document.querySelector('#sketch-frame').contentDocument.querySelector('#canvas').getContext('2d').getImageData(0,0,960,720).data.some(n=>n>0)",'saved shapes are drawn again');
 assert.equal((await storage())[0].sketch.items.filter(item=>['line','arrow'].includes(item.kind)).length,2);
 await click(await childPoint('#close'));
 await waitFor("!document.querySelector('#sketch-dialog').open",'shape editor closed');

 const relevantIssues=issues.filter(text=>!text.includes("image 'data:,'")&&!text.includes('net::ERR_EMPTY_RESPONSE'));
 assert.deepEqual(relevantIssues,[],'No editor script errors');
 console.log('PASS: draw, editable thumbnail, replacement, F5 persistence, legacy PNG re-edit, ordinary image zoom, close, reference count and CSP.');
}catch(e){
 console.error('FAIL: '+(e.stack||e)+'\nBrowser issues: '+issues.join('\n'));
 process.exitCode=1;
}finally{
 if(ws)ws.close();
 chrome.kill('SIGTERM');
 await sleep(220);
 rmSync(temp,{recursive:true,force:true,maxRetries:3});
}