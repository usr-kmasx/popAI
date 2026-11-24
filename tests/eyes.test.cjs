const assert=require('node:assert/strict');
const {gaze}=require('../web/eyes.js');
for(const [w,h,pw,ph] of [[51,28,26,8.5],[38,20,19,6]]){
  for(const [dx,dy] of [[0,0],[100,0],[-100,0],[0,100],[0,-100],[1000,1000]]){
    const p=gaze(dx,dy,w,h,pw,ph);
    assert.ok(Math.abs(p.x)<=w/2-pw/2);
    assert.ok(Math.abs(p.y)<=h/2-ph/2);
    if(dx)assert.equal(Math.sign(p.x),Math.sign(dx));
    if(dy)assert.equal(Math.sign(p.y),Math.sign(dy));
  }
}
const fs=require('node:fs'),vm=require('node:vm');
const pupil={offsetWidth:26,offsetHeight:8.5,style:{}};
const mascot={style:{},dataset:{},addEventListener(){},querySelectorAll:()=>[{getBoundingClientRect:()=>({left:16,top:90,width:51,height:28}),firstElementChild:pupil}]};
const events={},frames=[];
vm.runInNewContext(fs.readFileSync('web/eyes.js','utf8'),{
  document:{addEventListener(){},getElementById:()=>mascot,querySelector:selector=>selector==='#form'?({getClientRects:()=>[{}],getBoundingClientRect:()=>({left:400,right:800,top:300,bottom:400})}):null},
  setTimeout:()=>1,clearTimeout:()=>{},matchMedia:()=>({matches:false,addEventListener(){}}),MutationObserver:class{observe(){}},
  addEventListener:(n,f)=>{events[n]=f},
  requestAnimationFrame:f=>{frames.push(f);return frames.length;}
});
frames.shift()();
const initial=pupil.style.transform;
for(const x of [600,0,1200,60]){
  events.pointermove({pointerType:'mouse',clientX:x,clientY:350});frames.shift()();
  assert.notEqual(pupil.style.transform,initial);
  assert.deepEqual(mascot.style,{});
  assert.equal(mascot.dataset.iris,x===600?'flat':'round');
}
events.pointerout({relatedTarget:null});frames.shift()();
assert.equal(pupil.style.transform,initial);
assert.equal(mascot.dataset.iris,'round');
mascot.dataset.corrector='active';
events.pointermove({pointerType:'mouse',clientX:600,clientY:350});frames.shift()();
assert.equal(mascot.dataset.iris,'flat');
console.log('Fixed mascot, bounded pupil tracking and reset passed.');
