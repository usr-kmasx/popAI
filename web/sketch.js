(()=>{
'use strict';
if (window.parent !== window) document.documentElement.classList.add('embedded');
const canvas=document.querySelector('#canvas'),ctx=canvas.getContext('2d'),W=960,H=720;
const $=selector=>document.querySelector(selector);
const buttons=[...document.querySelectorAll('.tool[data-tool]')],swatches=[...document.querySelectorAll('[data-color]')];
let mode='pen',shape='rect',ink='#ffffff',items=[],states=[[]],step=0,current=null,gesture=null,selected=-1,entryPos=null,toastTimer=null;
let basePNG=null,baseImage=null;
const poseImages=new Map();
const copy=value=>JSON.parse(JSON.stringify(value)),brush=()=>Number($('#size').value)*2;
const refreshHistory=()=>{$('#undo').disabled=step===0;$('#redo').disabled=step===states.length-1;};
function tool(next){
 mode=next;buttons.forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tool===mode)));
 if(mode!=='move') selected=-1;
 updateSelection();
 canvas.style.cursor=mode==='move'?'default':mode==='text'?'text':mode==='eraser'?'cell':'crosshair';
 if(mode!=='shape')$('#shapes').hidden=true;
}
buttons.forEach(b=>b.onclick=()=>{
 if(b.dataset.tool==='shape'){const open=mode==='shape'&&!$('#shapes').hidden;tool('shape');$('#shapes').hidden=open;}
 else {
  tool(b.dataset.tool);
  if(mode==='text' && $('#text-entry').hidden) addText({x:W/2,y:H/2});
 }
});
document.querySelectorAll('[data-shape]').forEach(b=>b.onclick=()=>{
 shape=b.dataset.shape;
 document.querySelectorAll('[data-shape]').forEach(o=>o.setAttribute('aria-pressed',String(o===b)));
 tool('shape');$('#shapes').hidden=true;
});
swatches.forEach(b=>b.onclick=()=>{
 ink=b.dataset.color;swatches.forEach(o=>o.setAttribute('aria-pressed',String(o===b)));
 $('#wheel').setAttribute('aria-pressed','false');
});
$('#wheel').onclick=()=>$('#custom').click();
$('#custom').oninput=e=>{
 ink=e.target.value;swatches.forEach(b=>b.setAttribute('aria-pressed','false'));
 $('#wheel').setAttribute('aria-pressed','true');
};
function pos(e){const r=canvas.getBoundingClientRect();return {
 x:Math.max(0,Math.min(W,(e.clientX-r.left)*W/r.width)),
 y:Math.max(0,Math.min(H,(e.clientY-r.top)*H/r.height))
};}
function draw(item){
 if(item.kind==='pose'){
  const im=poseImages.get(item.png);
  if(im)ctx.drawImage(im,item.x,item.y,item.w,item.h);
  return;
 }
 ctx.lineWidth=item.w;ctx.lineJoin='round';ctx.lineCap='round';ctx.strokeStyle=item.color;ctx.fillStyle=item.color;
 if(item.kind==='pen'||item.kind==='eraser'){
  ctx.globalCompositeOperation=item.kind==='eraser'?'destination-out':'source-over';
  ctx.beginPath();const pts=item.points;
  if(pts.length===1){ctx.arc(pts[0].x,pts[0].y,item.w/2,0,Math.PI*2);ctx.fill();}
  else{ctx.moveTo(pts[0].x,pts[0].y);for(let i=1;i<pts.length;i++)ctx.lineTo(pts[i].x,pts[i].y);ctx.stroke();}
  ctx.globalCompositeOperation='source-over';return;
 }
 if(item.kind==='text'){ctx.font='500 '+item.w+'px system-ui';ctx.textBaseline='top';ctx.fillText(item.value,item.x,item.y);return;}
 ctx.beginPath();const dx=item.b.x-item.a.x,dy=item.b.y-item.a.y;
 if(item.kind==='rect')ctx.rect(item.a.x,item.a.y,dx,dy);
 else if(item.kind==='line'||item.kind==='arrow'){
  ctx.moveTo(item.a.x,item.a.y);ctx.lineTo(item.b.x,item.b.y);
  if(item.kind==='arrow'){
   const head=arrowHead(item);
   if(head){for(const p of head){ctx.moveTo(item.b.x,item.b.y);ctx.lineTo(p.x,p.y);}}
  }
 } else ctx.ellipse((item.a.x+item.b.x)/2,(item.a.y+item.b.y)/2,Math.max(.01,Math.abs(dx)/2),Math.max(.01,Math.abs(dy)/2),0,0,Math.PI*2);
 ctx.stroke();
}
function shifted(item,dx,dy){
 const x=copy(item),shift=p=>{p.x+=dx;p.y+=dy;};
 if(x.points)x.points.forEach(shift);
 if(x.a){shift(x.a);shift(x.b);}
 if(x.kind==='text'||x.kind==='pose'){x.x+=dx;x.y+=dy;}return x;
}
function arrowHead(item){
 const dx=item.b.x-item.a.x,dy=item.b.y-item.a.y,dist=Math.hypot(dx,dy);
 if(dist<1)return null;
 const length=Math.min(dist*.48,Math.max(16,item.w*3));
 const angle=Math.atan2(dy,dx);
 return [-1,1].map(sign=>({
  x:item.b.x-length*Math.cos(angle+sign*Math.PI/6),
  y:item.b.y-length*Math.sin(angle+sign*Math.PI/6)
 }));
}
function itemBounds(item){
 if(item.kind==='pose')return {x:item.x,y:item.y,w:item.w,h:item.h};
 if(item.kind==='text'){
  ctx.font='500 '+item.w+'px system-ui';
  const width=ctx.measureText(item.value).width;
  return {x:item.x,y:item.y,w:Math.max(1,width),h:item.w*1.2};
 }
 const pad=item.w/2;
 if(item.kind==='line'||item.kind==='arrow'){
  const pts=[item.a,item.b,...(item.kind==='arrow'?arrowHead(item)||[]:[])];
  const xs=pts.map(p=>p.x),ys=pts.map(p=>p.y);
  return {x:Math.min(...xs)-pad,y:Math.min(...ys)-pad,
   w:Math.max(...xs)-Math.min(...xs)+2*pad,h:Math.max(...ys)-Math.min(...ys)+2*pad};
 }
 if(item.points){
  const xs=item.points.map(p=>p.x),ys=item.points.map(p=>p.y);
  return {x:Math.min(...xs)-pad,y:Math.min(...ys)-pad,
   w:Math.max(...xs)-Math.min(...xs)+2*pad,h:Math.max(...ys)-Math.min(...ys)+2*pad};
 }
 return {x:Math.min(item.a.x,item.b.x)-pad,y:Math.min(item.a.y,item.b.y)-pad,
  w:Math.abs(item.a.x-item.b.x)+2*pad,h:Math.abs(item.a.y-item.b.y)+2*pad};
}
function distanceToSegment(p,a,b){
 const dx=b.x-a.x,dy=b.y-a.y,den=dx*dx+dy*dy;
 const t=den?Math.max(0,Math.min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/den)):0;
 return Math.hypot(p.x-a.x-t*dx,p.y-a.y-t*dy);
}
function hitItem(item,p,inside=false){
 if(item.kind==='eraser')return false; // A borracha é uma operação, não um objeto selecionável.
 const b=itemBounds(item),slack=12;
 if(p.x<b.x-slack||p.x>b.x+b.w+slack||p.y<b.y-slack||p.y>b.y+b.h+slack)return false;
 if(item.kind==='text'||item.kind==='pose')return true;
 if(item.points){
  if(item.points.length===1)return Math.hypot(p.x-item.points[0].x,p.y-item.points[0].y)<=item.w/2+slack;
  return item.points.slice(1).some((b,i)=>distanceToSegment(p,item.points[i],b)<=item.w/2+slack);
 }
 if(item.kind==='line'||item.kind==='arrow'){
  const margin=item.w/2+slack;
  if(distanceToSegment(p,item.a,item.b)<=margin)return true;
  return item.kind==='arrow'&&(arrowHead(item)||[]).some(wing=>distanceToSegment(p,item.b,wing)<=margin);
 }
 const x1=Math.min(item.a.x,item.b.x),x2=Math.max(item.a.x,item.b.x);
 const y1=Math.min(item.a.y,item.b.y),y2=Math.max(item.a.y,item.b.y);
 const margin=item.w/2+slack;
 if(item.kind==='rect'){
  if(inside)return p.x>=x1&&p.x<=x2&&p.y>=y1&&p.y<=y2;
  return (Math.abs(p.x-x1)<=margin||Math.abs(p.x-x2)<=margin)&&p.y>=y1-margin&&p.y<=y2+margin
   ||(Math.abs(p.y-y1)<=margin||Math.abs(p.y-y2)<=margin)&&p.x>=x1-margin&&p.x<=x2+margin;
 }
 const rx=Math.max(.01,(x2-x1)/2),ry=Math.max(.01,(y2-y1)/2);
 const norm=Math.hypot((p.x-(x1+x2)/2)/rx,(p.y-(y1+y2)/2)/ry);
 return inside?norm<=1:Math.abs(norm-1)*Math.min(rx,ry)<=margin;
}
function hitTest(p){
 for(const inside of [false,true])
  for(let i=items.length-1;i>=0;i--)
   if(hitItem(items[i],p,inside))return i;
 return -1;
}
function scaledItem(item,bounds,corner,dx,dy){
 // The opposite corner remains anchored while the dragged corner changes size.
 const left=corner.includes('w'),top=corner.includes('n');
 const anchorX=left?bounds.x+bounds.w:bounds.x,anchorY=top?bounds.y+bounds.h:bounds.y;
 const sx=Math.min(8,Math.max(0.12,(bounds.w+(left?-dx:dx))/Math.max(1,bounds.w)));
 const sy=Math.min(8,Math.max(0.12,(bounds.h+(top?-dy:dy))/Math.max(1,bounds.h)));
 const result=copy(item);
 if(item.kind==='pose'){
  const scale=Math.min(8,Math.max(.12,Math.abs(dx)/Math.max(1,bounds.w)>Math.abs(dy)/Math.max(1,bounds.h)?sx:sy));
  result.w=item.w*scale;result.h=item.h*scale;
  result.x=left?anchorX-result.w:anchorX;result.y=top?anchorY-result.h:anchorY;
  return result;
 }
 if(item.kind==='text'){
  // Text keeps its font proportions; diagonal dragging changes its font size.
  const uniform=Math.min(8,Math.max(0.2,Math.sqrt(sx*sy)));
  result.x=anchorX+(item.x-anchorX)*uniform;
  result.y=anchorY+(item.y-anchorY)*uniform;
  result.w=item.w*uniform;
 }else{
  const transform=p=>{p.x=anchorX+(p.x-anchorX)*sx;p.y=anchorY+(p.y-anchorY)*sy;};
  if(result.points)result.points.forEach(transform);
  if(result.a){transform(result.a);transform(result.b);}
  result.w=item.w*Math.sqrt(sx*sy);
 }
 return result;
}
function activeItem(index){
 if(!gesture||gesture.index!==index)return items[index];
 if(gesture.kind==='resize')return scaledItem(gesture.original,gesture.bounds,gesture.corner,gesture.dx,gesture.dy);
 if(gesture.kind==='move')return shifted(items[index],gesture.dx,gesture.dy);
 return items[index];
}
function updateSelection(){
 const frame=$('#selection-box');
 if(mode!=='move'||selected<0||!items[selected]||items[selected].kind==='eraser'){
  frame.hidden=true;delete frame.dataset.index;return;
 }
 const b=itemBounds(activeItem(selected)),r=canvas.getBoundingClientRect(),board=$('#board').getBoundingClientRect();
 frame.style.left=(r.left-board.left+b.x*r.width/W)+'px';
 frame.style.top=(r.top-board.top+b.y*r.height/H)+'px';
 frame.style.width=Math.max(2,b.w*r.width/W)+'px';
 frame.style.height=Math.max(2,b.h*r.height/H)+'px';
 frame.hidden=false;frame.dataset.index=String(selected);
}
function repaint(){
 ctx.clearRect(0,0,W,H);
 if(baseImage) ctx.drawImage(baseImage,0,0,W,H);
 items.forEach((_,i)=>draw(activeItem(i)));
 if(current)draw(current);
 updateSelection();
}
document.querySelectorAll('.resize-handle').forEach(handle=>{
 handle.addEventListener('pointerdown',e=>{
  if(mode!=='move'||selected<0||gesture||e.button!==0)return;
  e.preventDefault();e.stopPropagation();
  const p=pos(e);
  gesture={kind:'resize',id:e.pointerId,index:selected,corner:handle.dataset.corner,
   original:copy(items[selected]),bounds:itemBounds(items[selected]),start:p,dx:0,dy:0};
  handle.setPointerCapture(e.pointerId);
 });
 handle.addEventListener('pointermove',e=>{
  if(!gesture||gesture.kind!=='resize'||gesture.id!==e.pointerId)return;
  const p=pos(e);
  gesture.dx=p.x-gesture.start.x;
  gesture.dy=p.y-gesture.start.y;
  repaint();
 });
 const done=(e,cancelled=false)=>{
  if(!gesture||gesture.kind!=='resize'||gesture.id!==e.pointerId)return;
  const g=gesture;
  gesture=null;
  if(!cancelled&&(Math.abs(g.dx)+Math.abs(g.dy)>1)){
   items[g.index]=scaledItem(g.original,g.bounds,g.corner,g.dx,g.dy);
   save();
  }else repaint();
 };
 handle.addEventListener('pointerup',e=>done(e));
 handle.addEventListener('pointercancel',e=>done(e,true));
});
function save(){states.splice(step+1);states.push(copy(items));step=states.length-1;refreshHistory();repaint();}
function undo(){if(step>0){step--;items=copy(states[step]);selected=-1;refreshHistory();repaint();}}
function redo(){if(step<states.length-1){step++;items=copy(states[step]);selected=-1;refreshHistory();repaint();}}
$('#undo').onclick=undo;$('#redo').onclick=redo;
function addText(p){
 const entry=$('#text-entry');
 if(!entry.hidden) finishText();
 entryPos=p;
 entry.hidden=false;entry.value='';entry.style.color=ink;
 entry.style.fontSize=Math.max(14,Math.round(Math.max(25,brush()*2.5)*canvas.getBoundingClientRect().width/W))+'px';
 const rect=entry.getBoundingClientRect();
 const board=canvas.getBoundingClientRect();
 entry.style.left=Math.max(8,Math.min(p.x/W*board.width,board.width-rect.width-8))+'px';
 entry.style.top=Math.max(8,Math.min(p.y/H*board.height,board.height-rect.height-8))+'px';
 entry.focus();
}
function finishText(){
 const field=$('#text-entry');if(field.hidden)return;
 const value=field.value.trim();field.hidden=true;
 if(value){items.push({kind:'text',x:entryPos.x,y:entryPos.y,color:ink,w:Math.max(25,brush()*2.5),value});save();}
}
$('#text-entry').onkeydown=e=>{
 if(e.key==='Enter'){e.preventDefault();finishText();}
 if(e.key==='Escape'){e.preventDefault();$('#text-entry').hidden=true;}
};
$('#text-entry').onblur=finishText;
canvas.onpointerdown=e=>{
 if(e.button!==0||gesture)return;
 $('#shapes').hidden=true;const p=pos(e);
 if(mode==='text')return;
 if(mode==='move'){
  selected=hitTest(p);
  updateSelection();
  if(selected<0){canvas.style.cursor='default';return;}
 }
 gesture={kind:mode==='move'?'move':'draw',id:e.pointerId,start:p,index:mode==='move'?selected:-1,dx:0,dy:0};
 if(mode==='pen'||mode==='eraser')current={kind:mode,color:ink,w:brush(),points:[p]};
 else if(mode==='shape')current={kind:shape,color:ink,w:brush(),a:p,b:p};
 canvas.setPointerCapture(e.pointerId);
 if(mode==='move')canvas.style.cursor='grabbing';
 repaint();
};
canvas.onpointermove=e=>{
 if(!gesture){
  if(mode==='move')canvas.style.cursor=hitTest(pos(e))<0?'default':'grab';
  return;
 }
 if(e.pointerId!==gesture.id)return;
 const p=pos(e);
 if(mode==='move'){gesture.dx=p.x-gesture.start.x;gesture.dy=p.y-gesture.start.y;}
 else if(current){if(current.points)current.points.push(p);else current.b=p;}
 repaint();
};
function end(e,cancelled){
 if(!gesture||e.pointerId!==gesture.id)return;
 if(!cancelled){
  if(mode==='move'){
   if(gesture.index>=0&&Math.abs(gesture.dx)+Math.abs(gesture.dy)>1){
    items[gesture.index]=shifted(items[gesture.index],gesture.dx,gesture.dy);
    gesture=null;save();
   }
  }else if(current){items.push(current);gesture=null;save();}
 }
 gesture=null;current=null;
 canvas.style.cursor=mode==='move'?'grab':canvas.style.cursor;
 repaint();
}
canvas.onclick=e=>{if(mode==='text')addText(pos(e));};
canvas.onpointerup=e=>end(e,false);canvas.onpointercancel=e=>end(e,true);
canvas.oncontextmenu=e=>e.preventDefault();
document.addEventListener('keydown',e=>{
 if(e.target===$('#text-entry'))return;
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();e.shiftKey?redo():undo();}
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();redo();}
 if((e.key==='Delete'||e.key==='Backspace')&&mode==='move'&&selected>=0){e.preventDefault();items.splice(selected,1);selected=-1;save();}
 if(e.key==='Escape'){$('#shapes').hidden=true;selected=-1;updateSelection();}
});
$('#open-pose').onclick=()=>window.parent.postMessage({type:'popai-sketch:pose'},location.origin);
window.addEventListener('message',async event=>{
 if(event.source!==window.parent||event.origin!==location.origin||event.data?.type!=='popai-sketch:insert-pose')return;
 try{
  const blob=event.data.blob;
  if(!(blob instanceof Blob)||blob.type!=='image/png'||blob.size>25*1024*1024)return;
  const im=await createImageBitmap(blob);
  const source=document.createElement('canvas');
  const rasterScale=Math.min(1,960/Math.max(im.width,im.height));
  source.width=Math.max(1,Math.round(im.width*rasterScale));source.height=Math.max(1,Math.round(im.height*rasterScale));
  const c=source.getContext('2d');c.drawImage(im,0,0,source.width,source.height);im.close();
  // Tight bounds around the pose so the selection matches the visible body.
  const pixels=c.getImageData(0,0,source.width,source.height).data;
  let x1=source.width,y1=source.height,x2=-1,y2=-1;
  for(let y=0;y<source.height;y++)for(let x=0;x<source.width;x++)if(pixels[(y*source.width+x)*4+3]>15){x1=Math.min(x1,x);y1=Math.min(y1,y);x2=Math.max(x2,x);y2=Math.max(y2,y);}
  if(x2<x1||y2<y1)throw Error('Empty pose');
  const crop=document.createElement('canvas');crop.width=x2-x1+1;crop.height=y2-y1+1;
  crop.getContext('2d').drawImage(source,x1,y1,crop.width,crop.height,0,0,crop.width,crop.height);
  const png=crop.toDataURL('image/png');
  const scale=Math.min(W*.85/crop.width,H*.85/crop.height);
  const w=crop.width*scale,h=crop.height*scale;
  const item={kind:'pose',png,x:(W-w)/2,y:(H-h)/2,w,h};
  if(JSON.stringify({...sketchState(),items:[...items,item]}).length>2000000)throw Error('Sketch storage limit reached');
  poseImages.set(png,crop);
  items.push(item);selected=items.length-1;tool('move');save();notice('Pose inserted · move or resize it');
 }catch(error){notice(error.message);}
});
$('#close').onclick=()=>{
 if(window.parent!==window){window.parent.postMessage({type:'popai-sketch:close'},location.origin);return;}
 $('#editor').hidden=true;$('#closed').hidden=false;
};
$('#reopen').onclick=()=>{$('#editor').hidden=false;$('#closed').hidden=true;repaint();};
function notice(msg){const t=$('#toast');t.textContent=msg;t.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.hidden=true,4300);}
function validSketch(state){
 if(!state || state.version!==1 || !Array.isArray(state.items) || state.items.length>1500)return false;
 if(state.base!=null && (typeof state.base!=='string'||state.base.length>1600000||!/^data:image\/png;base64,[a-zA-Z0-9+/=]+$/.test(state.base)))return false;
 const validPoint=p=>p && Number.isFinite(p.x)&&Number.isFinite(p.y)&&Math.abs(p.x)<100000&&Math.abs(p.y)<100000;
 return state.items.every(item=>{
  if(item?.kind==='pose')return typeof item.png==='string'&&item.png.length<=1600000&&/^data:image\/png;base64,[a-zA-Z0-9+/=]+$/.test(item.png)&&[item.x,item.y,item.w,item.h].every(Number.isFinite)&&item.w>0&&item.h>0&&item.w<=20000&&item.h<=20000&&Math.abs(item.x)<100000&&Math.abs(item.y)<100000;
  if(!item || !['pen','eraser','rect','ellipse','line','arrow','text'].includes(item.kind)
      || !Number.isFinite(item.w) || item.w<0.05 || item.w>20000
      || !/^#[0-9a-f]{6}$/i.test(item.color))return false;
  if(item.kind==='text')return Number.isFinite(item.x)&&Number.isFinite(item.y)&&typeof item.value==='string'&&item.value.length<=140;
  if(item.kind==='pen'||item.kind==='eraser')
   return Array.isArray(item.points)&&item.points.length>0&&item.points.length<=20000&&item.points.every(validPoint);
  return validPoint(item.a)&&validPoint(item.b);
 });
}
window.addEventListener('message',async event=>{
 if(window.parent===window || event.source!==window.parent || event.origin!==location.origin || event.data?.type!=='popai-sketch:load')return;
 const state=event.data.state;
 if(!validSketch(state))return;
 basePNG=null;baseImage=null;
 if(state.base){
  try{
   const raw=atob(state.base.slice('data:image/png;base64,'.length));
   const bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));
   baseImage=await createImageBitmap(new Blob([bytes],{type:'image/png'}));
   basePNG=state.base;
  }catch{basePNG=null;baseImage=null;}
 }
 poseImages.clear();
 for(const item of state.items.filter(item=>item.kind==='pose')){
  try{
   const raw=atob(item.png.slice('data:image/png;base64,'.length));
   poseImages.set(item.png,await createImageBitmap(new Blob([Uint8Array.from(raw,c=>c.charCodeAt(0))],{type:'image/png'})));
  }catch{}
 }
 items=copy(state.items);states=[copy(items)];step=0;selected=-1;current=null;gesture=null;
 if(typeof state.color==='string'&&/^#[0-9a-f]{6}$/i.test(state.color))ink=state.color;
 if(Number.isFinite(state.size))$('#size').value=String(Math.max(1,Math.min(32,state.size)));
 if(['rect','ellipse','line','arrow'].includes(state.shape))shape=state.shape;
 swatches.forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.color===ink)));
 $('#wheel').setAttribute('aria-pressed',String(!swatches.some(button=>button.dataset.color===ink)));
 refreshHistory();repaint();
});
function sketchState(){return {version:1,items:copy(items),color:ink,size:Number($('#size').value),shape,...(basePNG?{base:basePNG}:{})};}
$('#confirm').onclick=()=>{
 const image=document.createElement('canvas');image.width=W;image.height=H;
 const c=image.getContext('2d');c.fillStyle='#202121';c.fillRect(0,0,W,H);c.drawImage(canvas,0,0);
 image.toBlob(blob=>{
  if(!blob){notice('Falha ao exportar o desenho');return;}
  if(window.parent!==window){window.parent.postMessage({type:'popai-sketch:submit',blob,state:sketchState()},location.origin);return;}
  const url=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=url;a.download='popai-sketch-4x3.png';document.body.append(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  notice('PNG 4:3 exportado · Ainda não conectado ao popAI.');
 },'image/png');
};
window.addEventListener('resize',updateSelection);
document.querySelectorAll('[data-color]').forEach(button=>{button.style.setProperty('--c',button.dataset.color);});
refreshHistory();repaint();
})();
