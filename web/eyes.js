/* Fixed mascot: pointer tracking and occasional idle expressions. */
(() => {
  'use strict';
  function gaze(dx,dy,w,h,pw,ph){
    const d=Math.max(48,Math.hypot(dx,dy));
    return {x:dx/d*Math.max(0,w/2-pw/2-4),y:dy/d*Math.max(0,h/2-ph/2-2)};
  }
  if(typeof module!=='undefined')module.exports={gaze};
  if(typeof document==='undefined')return;
  const mascot=document.getElementById('mascot');
  if(!mascot)return;
  const eyes=[...mascot.querySelectorAll('.eye')];
  const input=document.querySelector('#form');
  const brand=document.querySelector('.brand');
  const heading=document.querySelector('.welcome h1');
  let pointer=null,frame=0,idleLook=null,idleTimer=null;
  let blinkTimer=null;
  const reduceMotion=matchMedia('(prefers-reduced-motion: reduce)');
  function canBlink(){
    return !document.hidden&&!reduceMotion.matches&&mascot.dataset.corrector!=='active'&&mascot.dataset.enhancer!=='active'&&mascot.dataset.imageGenerating!=='true';
  }
  function scheduleBlink(delay=3000+Math.random()*5000){
    clearTimeout(blinkTimer);
    blinkTimer=setTimeout(()=>{
      if(!canBlink()){scheduleBlink();return;}
      const double=Math.random()<.13;
      function blink(again){
        if(!canBlink()){delete mascot.dataset.blink;scheduleBlink();return;}
        mascot.dataset.blink='true';
        blinkTimer=setTimeout(()=>{
          delete mascot.dataset.blink;
          if(again)blinkTimer=setTimeout(()=>blink(false),120+Math.random()*80);
          else scheduleBlink();
        },150);
      }
      blink(double);
    },delay);
  }
  function cancelBlink(){
    clearTimeout(blinkTimer);
    delete mascot.dataset.blink;
    scheduleBlink();
  }
  function inInput(){
    if(!pointer||!input||input.getClientRects().length===0)return false;
    const r=input.getBoundingClientRect();
    return pointer.x>=r.left&&pointer.x<=r.right&&pointer.y>=r.top&&pointer.y<=r.bottom;
  }
  function render(){
    frame=0;
    if(brand&&heading){
      const b=brand.getBoundingClientRect(),h=heading.getBoundingClientRect();
      const mobile=innerWidth<=640;
      const cornerX=b.left+b.width/2;
      const cornerY=b.bottom+(mobile?16:22)+(mobile?10:14);
      const centerY=h.height?Math.max(cornerY+26,h.top-76):innerHeight*.28;
      mascot.style.setProperty('--corner-x',cornerX+'px');
      mascot.style.setProperty('--corner-y',cornerY+'px');
      mascot.style.setProperty('--center-y',centerY+'px');
    }
    const processing=mascot.dataset.corrector==='active'||mascot.dataset.enhancer==='active'||mascot.dataset.imageGenerating==='true';
    const round=!processing&&!inInput()&&!idleLook;
    mascot.dataset.iris=round?'round':'flat';
    for(const eye of eyes){
      const r=eye.getBoundingClientRect(),p=eye.firstElementChild;
      const look=idleLook&&!inInput()?idleLook:pointer;
      const dx=look?look.x-r.left-r.width/2:0;
      const dy=look?look.y-r.top-r.height/2:0;
      const nativeWidth=eye.offsetWidth||r.width,nativeHeight=eye.offsetHeight||r.height;
      const small=nativeWidth<45;
      const pw=round?(small?10:14):(small?19:26);
      const ph=round?pw:(small?6:8.5);
      const offset=gaze(dx,dy,nativeWidth,nativeHeight,pw,ph);
      p.style.transform='translate(-50%,-50%) translate('+offset.x.toFixed(2)+'px,'+offset.y.toFixed(2)+'px)';
    }
  }
  function wake(){if(!frame)frame=requestAnimationFrame(render);}
  function scheduleIdle(){
    clearTimeout(idleTimer);
    idleTimer=setTimeout(()=>{
      if(!inInput()&&!document.hidden&&mascot.dataset.corrector!=='active'&&mascot.dataset.enhancer!=='active'&&mascot.dataset.imageGenerating!=='true'){
        const r=mascot.getBoundingClientRect(),angle=Math.random()*Math.PI*2;
        idleLook={x:r.left+r.width/2+Math.cos(angle)*160,y:r.top+r.height/2+Math.sin(angle)*160};
        wake();
        idleTimer=setTimeout(()=>{idleLook=null;wake();scheduleIdle();},1400+Math.random()*1700);
      }else scheduleIdle();
    },4500+Math.random()*6500);
  }
  function resetIdle(){idleLook=null;scheduleIdle();wake();}
  addEventListener('pointermove',e=>{
    if(e.pointerType==='touch')return;
    pointer={x:e.clientX,y:e.clientY};resetIdle();
  },{passive:true});
  addEventListener('pointerout',e=>{if(!e.relatedTarget){pointer=null;resetIdle();}},{passive:true});
  addEventListener('blur',()=>{pointer=null;resetIdle();});
  addEventListener('resize',wake,{passive:true});
  new MutationObserver(()=>{idleLook=null;if(!canBlink()&&mascot.dataset.blink)cancelBlink();wake();}).observe(mascot,{attributes:true,attributeFilter:['data-corrector','data-enhancer','data-image-generating','data-placement']});
  mascot.addEventListener('transitionend',e=>{if(e.target===mascot)wake();});
  reduceMotion.addEventListener('change',cancelBlink);
  document.addEventListener('visibilitychange',cancelBlink);
  scheduleBlink();
  scheduleIdle();
  wake();
})();
