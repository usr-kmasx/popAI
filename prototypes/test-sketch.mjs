import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtempSync,rmSync,readdirSync,statSync,mkdirSync,readFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {setTimeout as sleep} from 'node:timers/promises';

const root=dirname(fileURLToPath(import.meta.url));
const temp=mkdtempSync(join(root,'.test-browser-'));
const download=join(temp,'downloads');
mkdirSync(download);
const port=19321;
const child=spawn('chromium',[
 '--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-gpu',
 '--remote-allow-origins=*','--remote-debugging-port='+port,
 '--user-data-dir='+join(temp,'profile'),'--window-size=666,597',
 'http://127.0.0.1:7861/sketch.html'
],{stdio:'ignore'});
let ws,seq=0;
const pending=new Map();
async function waitForPort(){
 for(let i=0;i<80;i++){
  if(child.exitCode!==null)throw Error('Chromium exited');
  try{
   const data=await (await fetch('http://127.0.0.1:'+port+'/json')).json();
   const target=data.find(t=>t.type==='page'&&t.url.includes('sketch.html'));
   if(target)return target.webSocketDebuggerUrl;
  }catch{}
  await sleep(75);
 }
 throw Error('Chromium debugger timeout');
}
function call(method,params={}){
 const id=++seq;
 return new Promise((resolve,reject)=>{
  pending.set(id,{resolve,reject});
  ws.send(JSON.stringify({id,method,params}));
 });
}
async function evaluate(expression){
 const x=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
 if(x.result.exceptionDetails)throw Error(JSON.stringify(x.result.exceptionDetails));
 return x.result.result.value;
}
async function locate(selector){
 return evaluate('(()=>{const r=document.querySelector('+JSON.stringify(selector)+').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()');
}
async function mouse(type,p,buttons=0){
 await call('Input.dispatchMouseEvent',{type,x:p.x,y:p.y,button:'left',buttons,clickCount:1});
}
async function click(selector){
 const p=await locate(selector);await mouse('mousePressed',p,1);await mouse('mouseReleased',p);
}
async function key(key,code,modifiers=0){
 const vk=key==='Enter'?13:key==='Escape'?27:90;
 await call('Input.dispatchKeyEvent',{type:'keyDown',key,code,modifiers,windowsVirtualKeyCode:vk});
 await call('Input.dispatchKeyEvent',{type:'keyUp',key,code,modifiers,windowsVirtualKeyCode:vk});
}
const read=()=>evaluate("(()=>({tool:document.querySelector('.tool[aria-pressed=true]')?.dataset.tool,active:document.activeElement?.id,visible:!document.querySelector('#text-entry').hidden,text:document.querySelector('#text-entry').value,undo:document.querySelector('#undo').disabled,redo:document.querySelector('#redo').disabled,ink:document.querySelector('#canvas').getContext('2d').getImageData(0,0,960,720).data.reduce((s,n,i)=>s+(i%4===3&&n>0?1:0),0)}))()");
try{
 const endpoint=await waitForPort();
 ws=new WebSocket(endpoint);
 await new Promise((res,rej)=>{ws.onopen=res;ws.onerror=rej;});
 ws.onmessage=e=>{
  const m=JSON.parse(e.data);
  if(m.id&&pending.has(m.id)){
   const q=pending.get(m.id);pending.delete(m.id);
   m.error?q.reject(new Error(JSON.stringify(m.error))):q.resolve(m);
  }
 };
 await call('Page.enable');
 await call('Runtime.enable');
 await call('Page.setDownloadBehavior',{behavior:'allow',downloadPath:download});
 for(let i=0;i<60;i++){if(await evaluate("Boolean(document.querySelector('#text-entry'))"))break;await sleep(50);}
 assert.equal((await read()).visible,false);
 await click('[data-tool="text"]');
 let s=await read();
 assert.equal(s.visible,true,'Text input appears after clicking T');
 assert.equal(s.active,'text-entry','Text input is focused');
 await call('Input.insertText',{text:'Olá, popAI!'});
 assert.equal((await read()).text,'Olá, popAI!');
 await key('Enter','Enter');
 s=await read();
 assert.equal(s.visible,false,'Enter commits and closes text field');
 assert.equal(s.undo,false,'Text added to undo history');
 assert.ok(s.ink>100,'Text is actually drawn to canvas');
 const firstInk=s.ink;
 await key('z','KeyZ',2);
 assert.equal((await read()).ink,0,'Undo removes the text');
 await key('Z','KeyZ',10);
 assert.equal((await read()).ink,firstInk,'Ctrl Shift Z restores text');
 await click('[data-tool="text"]');
 assert.equal((await read()).visible,true);
 await call('Input.insertText',{text:'Cancelar'});
 await key('Escape','Escape');
 assert.equal((await read()).visible,false,'Escape closes field without saving');
 assert.equal((await read()).ink,firstInk,'Escape does not affect drawing');
 await click('#canvas');
 s=await read();
 assert.equal(s.visible,true,'Canvas click opens text');
 assert.equal(s.active,'text-entry','Canvas placement keeps focus');
 await call('Input.insertText',{text:'Mais texto'});
 await key('Enter','Enter');
 assert.ok((await read()).ink>firstInk,'Second text rendered');
 // The arrow must pick an individual item instead of translating the entire canvas.
 const canvasCoords=(x,y)=>evaluate("(()=>{const r=document.querySelector('#canvas').getBoundingClientRect();return {x:r.left+"+x+"/960*r.width,y:r.top+"+y+"/720*r.height}})()");
 const coverage=(x,y,w,h)=>evaluate("(()=>{const pixels=document.querySelector('#canvas').getContext('2d').getImageData("+x+","+y+","+w+","+h+").data;let n=0;for(let i=3;i<pixels.length;i+=4)if(pixels[i])n++;return n;})()");
 await mouse('mousePressed',await canvasCoords(200,560),1);
 await mouse('mouseReleased',await canvasCoords(200,560));
 await call('Input.insertText',{text:'Separado'});
 await key('Enter','Enter');
 const staticRegion=await coverage(465,353,300,75);
 const originalRegion=await coverage(198,555,175,70);
 assert.ok(originalRegion>30,'Third text is drawn away from other texts');
 await click('[data-tool="move"]');
 assert.equal((await read()).tool,'move');
 const grab=await canvasCoords(285,575);
 await mouse('mousePressed',grab,1);
 assert.equal(await evaluate("document.querySelector('#selection-box').dataset.index"),'2','The third text is selected individually');
 assert.equal(await evaluate("document.querySelector('#selection-box').hidden"),false,'Selection outline appears');
 await mouse('mouseReleased',grab);
 // Resizing text preserves font proportions, leaves other items unchanged and is undoable.
 const textBeforeResize=await evaluate("document.querySelector('#canvas').toDataURL()");
 const textStatic=await coverage(465,353,300,75);
 const textWidthBefore=await evaluate("parseFloat(document.querySelector('#selection-box').style.width)");
 const textHandle=await locate('.resize-handle[data-corner="se"]');
 await mouse('mousePressed',textHandle,1);
 await mouse('mouseMoved',{x:textHandle.x+28,y:textHandle.y+17},1);
 await mouse('mouseReleased',{x:textHandle.x+28,y:textHandle.y+17});
 assert.ok(await evaluate("parseFloat(document.querySelector('#selection-box').style.width)")>textWidthBefore+10,'Text can be enlarged with the handle');
 assert.equal(await coverage(465,353,300,75),textStatic,'Resizing does not alter other text');
 const textAfterResize=await evaluate("document.querySelector('#canvas').toDataURL()");
 assert.notEqual(textBeforeResize,textAfterResize,'Text resize changes output');
 await click('#undo');
 assert.equal(await evaluate("document.querySelector('#canvas').toDataURL()"),textBeforeResize,'Text resize can be undone');
 await click('#redo');
 assert.equal(await evaluate("document.querySelector('#canvas').toDataURL()"),textAfterResize,'Text resize can be redone');
 await click('#undo');
 await mouse('mousePressed',grab,1);
 assert.equal(await evaluate("document.querySelector('#selection-box').dataset.index"),'2','Undo restores hit testing for original text');
 await mouse('mouseReleased',grab);
 await mouse('mousePressed',grab,1);
 await mouse('mouseMoved',{x:grab.x+100,y:grab.y},1);
 await mouse('mouseReleased',{x:grab.x+100,y:grab.y});
 assert.equal(await coverage(465,353,300,75),staticRegion,'Other texts are not moved');
 assert.equal(await coverage(198,555,175,70),0,'Moved text leaves its original location');
 assert.ok(await coverage(458,555,200,70)>20,'Moved text appears at the new location');
 await click('#undo');
 assert.equal(await coverage(198,555,175,70),originalRegion,'Undo returns only the moved text');
 await click('#redo');
 assert.equal(await coverage(198,555,175,70),0,'Redo re-applies the single item movement');
 // Clicking empty space should deselect instead of dragging everything.
 await mouse('mousePressed',await canvasCoords(24,660),1);
 await mouse('mouseReleased',await canvasCoords(24,660));
 assert.equal(await evaluate("document.querySelector('#selection-box').hidden"),true,'Empty space deselects');
 await click('[data-tool="shape"]');
 assert.equal(await evaluate("document.querySelector('#shapes').hidden"),false);
 await click('[data-shape="rect"]');
 assert.equal((await read()).tool,'shape');
 const origin=await evaluate("(()=>{const r=document.querySelector('#canvas').getBoundingClientRect();return {x:r.left+40,y:r.top+40}})()");
 await mouse('mousePressed',origin,1);
 await mouse('mouseMoved',{x:origin.x+95,y:origin.y+82},1);
 await mouse('mouseReleased',{x:origin.x+95,y:origin.y+82});
 assert.equal((await read()).undo,false);
 const shapePixels=(await read()).ink;
 const unchangedText=await coverage(465,353,300,75);
 await click('[data-tool="move"]');
 const rectGrab={x:origin.x+56,y:origin.y+40};
 await mouse('mousePressed',rectGrab,1);
 assert.equal(await evaluate("document.querySelector('#selection-box').dataset.index"),'3','The rectangle is individually selectable');
 const rectLeft=Number(await evaluate("parseFloat(document.querySelector('#selection-box').style.left)"));
 await mouse('mouseMoved',{x:rectGrab.x+35,y:rectGrab.y},1);
 await mouse('mouseReleased',{x:rectGrab.x+35,y:rectGrab.y});
 const movedRectLeft=Number(await evaluate("parseFloat(document.querySelector('#selection-box').style.left)"));
 assert.ok(Math.abs(movedRectLeft-rectLeft-35)<1,'Only the rectangle moves 35 CSS pixels');
 assert.equal(await coverage(465,353,300,75),unchangedText,'Moving the rectangle preserves text');
 const movedRectImage=await evaluate("document.querySelector('#canvas').toDataURL()");
 await click('#undo');
 assert.equal((await read()).ink,shapePixels,'Undo restores rectangle placement');
 await click('#redo');
 assert.equal(await evaluate("document.querySelector('#canvas').toDataURL()"),movedRectImage,'Redo restores the moved rectangle');
 await click('#undo');
 // Corner handles resize only the selected rectangle; undo/redo recover its size.
 await mouse('mousePressed',rectGrab,1);
 await mouse('mouseReleased',rectGrab);
 assert.equal(await evaluate("document.querySelector('#selection-box').dataset.index"),'3');
 const boxSizeBefore=await evaluate("(()=>{const e=document.querySelector('#selection-box');return {w:parseFloat(e.style.width),h:parseFloat(e.style.height)}})()");
 const se=await locate('.resize-handle[data-corner="se"]');
 await mouse('mousePressed',se,1);
 await mouse('mouseMoved',{x:se.x+31,y:se.y+22},1);
 await mouse('mouseReleased',{x:se.x+31,y:se.y+22});
 const boxSizeAfter=await evaluate("(()=>{const e=document.querySelector('#selection-box');return {w:parseFloat(e.style.width),h:parseFloat(e.style.height)}})()");
 assert.ok(boxSizeAfter.w>boxSizeBefore.w+20&&boxSizeAfter.h>boxSizeBefore.h+10,'Rectangle expands horizontally and vertically');
 assert.equal(await coverage(465,353,300,75),unchangedText,'Rectangle resize does not affect text');
 const resizedRect=await evaluate("document.querySelector('#canvas').toDataURL()");
 await click('#undo');
 assert.equal((await read()).ink,shapePixels,'Undo returns original rectangle size');
 await click('#redo');
 assert.equal(await evaluate("document.querySelector('#canvas').toDataURL()"),resizedRect,'Redo restores rectangle resize');
 await click('#undo');
 // The opposite corner can also be dragged inward to shrink the object.
 await mouse('mousePressed',rectGrab,1);
 await mouse('mouseReleased',rectGrab);
 const nw=await locate('.resize-handle[data-corner="nw"]');
 const oldLeft=await evaluate("parseFloat(document.querySelector('#selection-box').style.left)");
 await mouse('mousePressed',nw,1);
 await mouse('mouseMoved',{x:nw.x+18,y:nw.y+16},1);
 await mouse('mouseReleased',{x:nw.x+18,y:nw.y+16});
 assert.ok(await evaluate("parseFloat(document.querySelector('#selection-box').style.left)")>oldLeft+10,'Top-left handle shrinks the rectangle');
 await click('#undo');
 assert.equal((await read()).ink,shapePixels,'Undo restores rectangle after shrinking');
 // Erasing across the rectangle must remove previously painted pixels.
 await click('[data-tool="eraser"]');
 await mouse('mousePressed',{x:origin.x+48,y:origin.y},1);
 await mouse('mouseMoved',{x:origin.x+60,y:origin.y+15},1);
 await mouse('mouseReleased',{x:origin.x+60,y:origin.y+15});
 assert.ok((await read()).ink<shapePixels,'Eraser clears some pixels');
 await click('#undo');
 assert.equal((await read()).ink,shapePixels,'Eraser is undoable');
 // The size slider and color palette affect the drawing.
 await click('[data-color="#e63838"]');
 assert.equal(await evaluate("document.querySelector('[data-color=\"#e63838\"]').getAttribute('aria-pressed')"),'true');
 await click('[data-tool="pen"]');
 assert.equal((await read()).tool,'pen');
 const beforePen=(await read()).ink;
 await mouse('mousePressed',{x:origin.x+120,y:origin.y+140},1);
 await mouse('mouseMoved',{x:origin.x+180,y:origin.y+143},1);
 await mouse('mouseReleased',{x:origin.x+180,y:origin.y+143});
 assert.ok((await read()).ink>beforePen,'Pen can draw after switching tools');
 await click('[data-tool="move"]');
 const beforeStrokeMove=await evaluate("document.querySelector('#canvas').toDataURL()");
 const strokeGrab={x:origin.x+150,y:origin.y+141.5};
 await mouse('mousePressed',strokeGrab,1);
 assert.equal(await evaluate("document.querySelector('#selection-box').dataset.index"),'4','The brush stroke is selected separately');
 await mouse('mouseMoved',{x:strokeGrab.x+40,y:strokeGrab.y},1);
 await mouse('mouseReleased',{x:strokeGrab.x+40,y:strokeGrab.y});
 const afterStrokeMove=await evaluate("document.querySelector('#canvas').toDataURL()");
 assert.notEqual(afterStrokeMove,beforeStrokeMove,'Moving a stroke changes the canvas');
 await click('#undo');
 assert.equal(await evaluate("document.querySelector('#canvas').toDataURL()"),beforeStrokeMove,'Undo restores stroke position');
 await click('#redo');
 assert.equal(await evaluate("document.querySelector('#canvas').toDataURL()"),afterStrokeMove,'Redo restores only stroke movement');
 const movedStrokeGrab={x:strokeGrab.x+40,y:strokeGrab.y};
 await mouse('mousePressed',movedStrokeGrab,1);
 await mouse('mouseReleased',movedStrokeGrab);
 assert.equal(await evaluate("document.querySelector('#selection-box').dataset.index"),'4','Moved stroke stays individually selectable');
 const penBeforeResize=await evaluate("document.querySelector('#canvas').toDataURL()");
 const penBoundsBefore=await evaluate("(()=>{const e=document.querySelector('#selection-box');return {w:parseFloat(e.style.width),h:parseFloat(e.style.height)}})()");
 const penHandle=await locate('.resize-handle[data-corner="se"]');
 await mouse('mousePressed',penHandle,1);
 await mouse('mouseMoved',{x:penHandle.x+40,y:penHandle.y+20},1);
 await mouse('mouseReleased',{x:penHandle.x+40,y:penHandle.y+20});
 const penBoundsAfter=await evaluate("(()=>{const e=document.querySelector('#selection-box');return {w:parseFloat(e.style.width),h:parseFloat(e.style.height)}})()");
 assert.ok(penBoundsAfter.w>penBoundsBefore.w+25,'A freehand stroke can be resized');
 const penAfterResize=await evaluate("document.querySelector('#canvas').toDataURL()");
 assert.notEqual(penBeforeResize,penAfterResize,'Stroke resize affects output');
 await click('#undo');
 assert.equal(await evaluate("document.querySelector('#canvas').toDataURL()"),penBeforeResize,'Undo restores stroke size');
 await click('#redo');
 assert.equal(await evaluate("document.querySelector('#canvas').toDataURL()"),penAfterResize,'Redo restores stroke size');
 const afterMove=(await read()).ink;
 await click('#close');
 assert.equal(await evaluate("document.querySelector('#editor').hidden"),true,'Close hides editor');
 await click('#reopen');
 assert.equal(await evaluate("document.querySelector('#editor').hidden"),false,'Reopen shows editor');
 assert.equal((await read()).ink,afterMove,'Reopen preserves drawing');
 await click('#confirm');
 for(let i=0;i<40&&!readdirSync(download).some(f=>f.endsWith('.png'));i++)await sleep(100);
 const f=readdirSync(download).find(f=>f.endsWith('.png'));
 assert.ok(f,'Confirm downloads PNG');
 assert.ok(statSync(join(download,f)).size>500,'Downloaded PNG has content');
 const png=readFileSync(join(download,f));
 assert.equal(png.subarray(0,8).toString('hex'),'89504e470d0a1a0a','Valid PNG signature');
 assert.equal(png.readUInt32BE(16),960,'PNG width');
 assert.equal(png.readUInt32BE(20),720,'PNG height');
 console.log('PASS: text focus, Unicode typing, Enter, Escape, position, undo/redo, shapes, pen, eraser, move, colors, window state, PNG export 960x720.');
}catch(e){
 console.error('FAIL:',e.stack||e.message);
 process.exitCode=1;
}finally{
 if(ws)ws.close();
 child.kill('SIGTERM');
 await sleep(250);
 rmSync(temp,{recursive:true,force:true,maxRetries:3});
}
