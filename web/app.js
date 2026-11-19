const mascot = document.querySelector('#mascot');
let mascotState = '';
let lastActivity = performance.now();
let completionAudio = null;
let lastSoundJob = null;
function prepareCompletionSound() {
  try {
    const AudioEngine=window.AudioContext || window.webkitAudioContext;
    if(!AudioEngine)return;
    if(!completionAudio)completionAudio=new AudioEngine();
    if(completionAudio.state==='suspended')completionAudio.resume().catch(()=>{});
  } catch {}
}
function playCompletionSound(identity) {
  if(!identity || lastSoundJob===identity)return;
  lastSoundJob=identity;
  if(!completionAudio || completionAudio.state!=='running')return;
  try {
    const note=completionAudio.createOscillator(),volume=completionAudio.createGain();
    const now=completionAudio.currentTime;
    note.type='sine';note.frequency.setValueAtTime(880,now);
    volume.gain.setValueAtTime(.0001,now);
    volume.gain.exponentialRampToValueAtTime(.12,now+.012);
    volume.gain.exponentialRampToValueAtTime(.0001,now+.35);
    note.connect(volume);volume.connect(completionAudio.destination);
    note.onended=()=>{note.disconnect();volume.disconnect();};
    note.start(now);note.stop(now+.4);
  } catch {}
}
function updateMascot() {
  const generating = Boolean(clockJob) || enhancing;
  if (mascotState === 'generating' && !generating) lastActivity = performance.now();
  const state = generating ? 'generating' : performance.now()-lastActivity >= 30000 ? 'waiting' : 'idle';
  if (state !== mascotState) {
    mascotState = state;
    mascot.src = {idle:'/mascot.svg',waiting:'/mascot-waiting.svg',generating:'/mascot-generating.svg'}[state];
  }
}
function wakeMascot() { lastActivity = performance.now(); updateMascot(); prepareCompletionSound(); }
document.addEventListener('pointerdown',wakeMascot,{passive:true});
document.addEventListener('keydown',wakeMascot);
const form = document.querySelector('#form');
const prompt = document.querySelector('#prompt');
const promptDraftKey = 'popai.prompt-draft';
const promptStateKey = 'popai.prompt-state';
function savePromptDraft() {
  try {
    window.localStorage.setItem(promptStateKey,JSON.stringify({version:1,text:prompt.value,undo:undoPrompt===null?null:{original:undoPrompt,enhanced:prompt.value}}));
    window.localStorage.removeItem(promptDraftKey);
  } catch {}
}
const stage = document.querySelector('.stage');
const status = document.querySelector('#status');
let wallpaper = document.querySelector('#wallpaper');
const imageViewport = document.querySelector('#image-viewport');
const generationPreview = document.querySelector('#generation-preview');
let previewEpoch = 0;
let displayedPreview = null;
let pendingPreview = null;
function clearGenerationPreview(restore = true) {
  previewEpoch++;
  displayedPreview = pendingPreview = null;
  if (restore && !generationPreview.hidden) welcome.hidden = !wallpaper.hidden;
  generationPreview.hidden = true;
  generationPreview.replaceChildren();
}
async function showGenerationPreview(job) {
  if (!job.preview) { clearGenerationPreview(); return; }
  if (displayedPreview === job.preview || pendingPreview === job.preview) return;
  const epoch = ++previewEpoch;
  pendingPreview = job.preview;
  const image = new Image();
  image.alt = '';
  image.draggable = false;
  image.src = job.preview;
  try {
    await image.decode();
    if (epoch !== previewEpoch) return;
    endImageDrag();
    if (!wallpaper.hidden) {
      wallpaper.removeAttribute('src');
      save.removeAttribute('href');
      shown = null;
    }
    wallpaper.hidden = save.hidden = welcome.hidden = true;
    imageViewport.classList.remove('has-image');
    generationPreview.replaceChildren(image);
    generationPreview.hidden = false;
    displayedPreview = job.preview;
  } catch {
    // A completed/cancelled job may remove its base while the preview loads.
  } finally {
    if (epoch === previewEpoch) pendingPreview = null;
  }
}
const imageView = {zoom:1,x:0,y:0,drag:null};
let imageViewSize = null;
function drawImageView() {
  const w=imageViewport.clientWidth,h=imageViewport.clientHeight;
  const iw=wallpaper.clientWidth*imageView.zoom,ih=wallpaper.clientHeight*imageView.zoom;
  if (w>0 && h>0 && iw>0 && ih>0) {
    const limitX=(w+iw)/2-Math.min(64,iw/2),limitY=(h+ih)/2-Math.min(64,ih/2);
    imageView.x=Math.max(-limitX,Math.min(limitX,imageView.x));
    imageView.y=Math.max(-limitY,Math.min(limitY,imageView.y));
  }
  wallpaper.style.transform = `translate(-50%, -50%) translate(${imageView.x}px, ${imageView.y}px) scale(${imageView.zoom})`;
}
function endImageDrag() {
  const drag = imageView.drag;
  imageView.drag = null;
  imageViewport.classList.remove('dragging');
  if (drag && imageViewport.hasPointerCapture(drag.id)) imageViewport.releasePointerCapture(drag.id);
}
function resetImageView() {
  endImageDrag();
  imageView.zoom = 1;
  imageView.x = imageView.y = 0;
  drawImageView();
}
function resizeImageView() {
  const w=imageViewport.clientWidth,h=imageViewport.clientHeight;
  if (!(w>0 && h>0)) return;
  if (imageViewSize && !wallpaper.hidden) {
    imageView.x *= w/imageViewSize.w;
    imageView.y *= h/imageViewSize.h;
  }
  imageViewSize={w,h};
  drawImageView();
}
window.addEventListener('resize',resizeImageView);
imageViewport.addEventListener('wheel',event => {
  if (wallpaper.hidden) return;
  event.preventDefault();
  const bounds = imageViewport.getBoundingClientRect();
  const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? bounds.height : 1;
  const factor = Math.exp(Math.max(-1,Math.min(1,-event.deltaY*unit*.002)));
  const zoom = Math.max(.2,Math.min(8,imageView.zoom*factor));
  const ratio = zoom/imageView.zoom;
  const x = event.clientX-bounds.left-bounds.width/2;
  const y = event.clientY-bounds.top-bounds.height/2;
  imageView.x = x-(x-imageView.x)*ratio;
  imageView.y = y-(y-imageView.y)*ratio;
  imageView.zoom = zoom;
  drawImageView();
},{passive:false});
imageViewport.addEventListener('pointerdown',event => {
  if (wallpaper.hidden || event.button !== 0 || event.isPrimary === false) return;
  event.preventDefault();
  imageViewport.focus({preventScroll:true});
  imageViewport.setPointerCapture(event.pointerId);
  imageView.drag = {id:event.pointerId,x:event.clientX,y:event.clientY};
  imageViewport.classList.add('dragging');
});
imageViewport.addEventListener('pointermove',event => {
  const drag = imageView.drag;
  if (!drag || event.pointerId !== drag.id) return;
  imageView.x += event.clientX-drag.x;
  imageView.y += event.clientY-drag.y;
  drag.x = event.clientX;
  drag.y = event.clientY;
  drawImageView();
});
for (const type of ['pointerup','pointercancel','lostpointercapture']) imageViewport.addEventListener(type,event => {
  if (imageView.drag?.id === event.pointerId) endImageDrag();
});
imageViewport.addEventListener('dblclick',event => {
  if (wallpaper.hidden) return;
  event.preventDefault();
  resetImageView();
});
imageViewport.addEventListener('keydown',event => {
  if (!wallpaper.hidden && ['Home','Escape'].includes(event.key)) { event.preventDefault(); resetImageView(); }
});
const welcome = document.querySelector('#welcome');
const save = document.querySelector('#save');
const addReference = document.querySelector('#add-reference');
const referenceFile = document.querySelector('#reference-file');
const referencePreview = document.querySelector('#reference-preview');
const modelButton = document.querySelector('#model-button');
const modelDialog = document.querySelector('#model-dialog');
const modelProfile = document.querySelector('#model-profile');
const modelStatus = document.querySelector('#model-status');
const modelApply = document.querySelector('#model-apply');
const outputAspect = document.querySelector('#output-aspect');
const generationSize = document.querySelector('#generation-size');
const outputResolution = document.querySelector('#output-resolution');
const adaptiveWeights = document.querySelector('#adaptive-weights');
const keepLoaded = document.querySelector('#keep-loaded');
const keepStatus = document.querySelector('#keep-status');
const timeEstimate = document.querySelector('#time-estimate');
const estimateArc = document.querySelector('#eta-arc');
function renderEstimate(job) {
  timeEstimate.hidden = job.state !== 'running' || job.phase === 'cancelling';
  if (timeEstimate.hidden) return;
  const progress = job.progress || {};
  const total = Number(progress.total);
  const completed = Number(progress.completed);
  const sampling = job.phase === 'generating' && progress.stage === 'sampling' && progress.unit === 'steps' && total > 0;
  const remaining = Number(progress.remaining_seconds);
  const upscaling = job.phase === 'upscaling' && job.upscale_passes !== 2 && progress.unit === 'percent' && total > 0;
  const measured = sampling || upscaling;
  estimateArc.hidden = !measured;
  estimateArc.setAttribute('stroke-dashoffset',String(measured ? 100*(1-Math.min(completed/total,1)) : 100));
  let message = job.phase === 'upscaling' ? 'Ampliando imagem' : job.phase === 'finalizing' ? 'Salvando imagem' : 'Preparando geração';
  if (job.phase === 'generating' && progress.stage === 'vae_decode') message = 'Decodificando imagem';
  if (sampling) message = completed >= total ? `${completed}/${total} · Finalizando imagem base` : `${completed}/${total} · ≈ ${formatDuration(remaining)}`;
  if (upscaling) message = `${Math.floor(completed)}% · ${progress.remaining_seconds == null ? 'Ampliando imagem' : completed >= total ? 'Finalizando ampliação' : `≈ ${formatDuration(remaining)}`}`;
  timeEstimate.title = message;
  timeEstimate.setAttribute('aria-label',message);
}
let clockJob = null;
let clockAnchor = 0;
let clockElapsed = 0;
function syncClock(job) {
  if (job.state !== 'running') { clockJob = null; updateMascot(); return; }
  const now = performance.now();
  const previous = clockJob?.id === job.id ? clockElapsed + (now-clockAnchor)/1000 : 0;
  clockElapsed = Math.max(Number(job.elapsed)||0,previous);
  clockAnchor = now;
  clockJob = job;
  tickClock();
}
function tickClock() {
  updateMascot();
  if (!clockJob) return;
  const delta = Math.max(0,(performance.now()-clockAnchor)/1000);
  const phase = clockJob.phase === 'cancelling' ? 'Cancelando' : clockJob.phase === 'upscaling' ? 'Ampliando com IA' : clockJob.phase === 'finalizing' ? 'Salvando PNG final' : 'Gerando imagem';
  status.textContent = `${phase} · ${formatDuration(Math.floor(clockElapsed+delta))}`;
  const progress = {...clockJob.progress};
  if (progress.remaining_seconds != null) progress.remaining_seconds = Math.max(0,progress.remaining_seconds-delta);
  renderEstimate({...clockJob,progress});
}
window.setInterval(tickClock,200);
const cancelGeneration = document.querySelector('#cancel-generation');
const modelSlots = Object.fromEntries(['diffusion', 'encoder', 'vae', 'vision'].map(key => [key, document.querySelector(`#model-${key}`)]));
let modelRootPaths = [];
const refreshModels = document.querySelector('#refresh-models');
const hardwareInputs = Object.fromEntries(['device','upscale_device','compatibility'].map(key => [key,document.querySelector('#hardware-' + key.replaceAll('_','-'))]));
const hardwareStatus = document.querySelector('#hardware-status');
let modelFiles = [];
let modelCatalog = null;
let customDraft = null;
let customModel = {};
let activeFamily = 'z-image-turbo';
let currentFamily = 'z-image-turbo';
const sdInputs = Object.fromEntries(['steps','cfg','sampler','scheduler','vae_tiling','vae_tile_size','mmap'].map(key => [key,document.querySelector('#sd-' + key.replaceAll('_','-'))]));
const generalTab = document.querySelector('#tab-general');
const sdTab = document.querySelector('#tab-sd');
const modelsTab = document.querySelector('#tab-models');
function selectTab(name) {
  for (const [key,button] of [['general',generalTab],['sd',sdTab],['models',modelsTab]]) {
    document.querySelector('#panel-'+key).hidden = name !== key;
    button.setAttribute('aria-selected',String(name === key));
  }
}
generalTab.addEventListener('click',() => selectTab('general'));
sdTab.addEventListener('click',() => selectTab('sd'));
modelsTab.addEventListener('click',() => { selectTab('models'); loadLibrary(); });
function readSd() {
  return Object.fromEntries(Object.entries(sdInputs).map(([key,input]) => [key, ['vae_tiling','mmap'].includes(key) ? input.checked : ['steps','cfg','vae_tile_size'].includes(key) ? Number(input.value) : input.value]));
}
function writeSd(value) {
  for (const [key,input] of Object.entries(sdInputs)) {
    if (['vae_tiling','mmap'].includes(key)) input.checked = value[key];
    else input.value = value[key];
  }
}
function markSamplingCustom() {
  customDraft = readSd();
  customModel = {profile:activeFamily,...Object.fromEntries(['diffusion','encoder','vae','vision'].map(key => [key,modelSlots[key].value]))};
  modelProfile.value = 'custom';
  modelStatus.textContent = '';
}
for (const input of Object.values(sdInputs)) input.addEventListener('input',markSamplingCustom);
let configuring = false;
let busy = false;
let running = false;
let stopping = false;
let uploading = false;
let enhancing = false;
let enhanceController = null;
let enhancerState = {state:'loading'};
let undoPrompt = null;
let modelsReady = true;
let observedJobKey = null;
let promptNotice = null;
function showPromptNotice(text) {
  promptNotice={text,jobKey:observedJobKey};
  status.textContent=text;
}
const enhancePrompt = document.querySelector('#enhance-prompt');
const cancelEnhance = document.querySelector('#cancel-enhance');
const undoEnhance = document.querySelector('#undo-enhance');
let references = [];
let shown = null;
let initialStatusReceived = false;
let hiddenImageId = null;
let resultError = null;
let recoverableJob = null;
const retryFinalize = document.querySelector('#retry-finalize');
retryFinalize.addEventListener('click', async () => {
  if (busy || !recoverableJob) return;
  setBusy(true);
  try { await request(`/api/jobs/${recoverableJob}/retry-finalize`, {method:'POST'}); }
  catch (error) { status.textContent = error.message; setBusy(false); }
});

function formatDuration(elapsed) {
  const seconds = Math.max(0, Math.round(Number(elapsed) || 0));
  return `${Math.floor(seconds / 60)}min ${seconds % 60}s`;
}

async function request(path, options) {
  const response = await fetch(path, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'Não foi possível acessar o servidor.');
  return body;
}

function setBusy(value = running) {
  running = value;
  busy = value || uploading || configuring || enhancing;
  refreshModels.disabled = busy;
  Object.values(hardwareInputs).forEach(input => { input.disabled = busy; });
  Object.values(sdInputs).forEach(input => { input.disabled = busy; });
  adjustConfig.disabled = busy;
  retryFinalize.disabled = busy;
  prompt.disabled = busy;
  addReference.disabled = busy || currentFamily === 'z-image-turbo';
  addReference.hidden = false;
  addReference.title = currentFamily !== 'z-image-turbo' ? 'Adicionar imagem de referência' : 'Referências indisponíveis neste modelo';
  referencePreview.querySelectorAll('button').forEach(button => { button.disabled = busy; });
  modelButton.disabled = uploading || configuring || stopping || enhancing;
  modelApply.disabled = busy;
  modelProfile.disabled = busy;
  outputResolution.disabled = busy;
  outputAspect.disabled = busy;
  generationSize.disabled = busy;
  Object.values(modelSlots).forEach(select => { select.disabled = busy; });
  keepLoaded.disabled = uploading || configuring || stopping;
  cancelGeneration.hidden = !running;
  cancelGeneration.disabled = stopping;
  stage.classList.toggle('busy', busy);
  form.setAttribute('aria-busy', String(busy));
  enhancePrompt.hidden = busy;
  undoEnhance.hidden = busy || undoPrompt === null;
  undoEnhance.disabled = busy;
  enhancePrompt.disabled = busy || !['ready','error','stopped'].includes(enhancerState.state) || enhancerState.busy || !prompt.value.trim();
  enhancePrompt.title = enhancing ? 'Melhorando prompt…' : enhancerState.state === 'ready' ? 'Melhorar prompt' : enhancerState.state==='error' || enhancerState.state==='stopped' ? 'Tentar melhorar prompt novamente' : 'Carregando melhorador…';
  enhancePrompt.classList.toggle('enhancing',enhancing);
  enhancePrompt.setAttribute('aria-busy',String(enhancing));
  cancelEnhance.hidden = !enhancing;
}

enhancePrompt.addEventListener('click',async()=>{
  if (busy || !prompt.value.trim() || !['ready','error','stopped'].includes(enhancerState.state)) return;
  const original=prompt.value;
  const originalUndo=undoPrompt;
  savePromptDraft();
  let text='',pending='',done=false;
  undoPrompt=null;undoEnhance.hidden=true;
  promptNotice=null;
  enhancing=true;enhanceController=new AbortController();setBusy();updateMascot();
  status.textContent='Melhorando prompt…';stage.classList.remove('error');
  try {
    const response=await fetch('/api/enhance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:original,editing:references.length>0}),signal:enhanceController.signal});
    if(!response.ok) {const error=await response.json();throw new Error(error.error || 'Não foi possível melhorar o prompt.');}
    if(!response.body)throw new Error('O navegador não recebeu o texto do melhorador.');
    const reader=response.body.getReader(),decoder=new TextDecoder();
    function receive(line) {
      if(!line.trim())return;
      const event=JSON.parse(line);
      if(event.error)throw new Error(event.error);
      if(event.text) {text+=event.text;prompt.value=text;resizePrompt();prompt.scrollTop=prompt.scrollHeight;}
      if(event.state==='done') {done=true;showPromptNotice(`Prompt melhorado · ${event.seconds.toLocaleString('pt-BR')}s`);}
    }
    while(true) {
      const chunk=await reader.read();
      if(chunk.done){pending+=decoder.decode();if(pending.trim())receive(pending);break;}
      pending+=decoder.decode(chunk.value,{stream:true});
      const lines=pending.split('\n');pending=lines.pop();lines.forEach(receive);
    }
    if(!done || !text.trim())throw new Error('A melhoria foi interrompida. O texto original foi restaurado.');
    prompt.value=text.trim();undoPrompt=original;
  } catch(error) {
    enhanceController.abort();prompt.value=original;undoPrompt=originalUndo;
    showPromptNotice(error.name==='AbortError'?'Melhoria cancelada · Texto original restaurado':error.message);
  } finally {
    enhancing=false;enhanceController=null;savePromptDraft();resizePrompt();setBusy();updateMascot();prompt.focus();
  }
});
cancelEnhance.addEventListener('click',()=>{
  enhanceController?.abort();
  request('/api/enhance/cancel',{method:'POST'}).catch(()=>{});
});
undoEnhance.addEventListener('click',()=>{
  if(busy || undoPrompt===null)return;
  prompt.value=undoPrompt;undoPrompt=null;undoEnhance.hidden=true;savePromptDraft();resizePrompt();setBusy();prompt.focus();showPromptNotice('Texto original restaurado');
});

const discardedReferences=new Set();
let releasingReferences=false;
function releaseReferences(ids,unloading=false) {
  ids.forEach(id=>discardedReferences.add(id));
  if(releasingReferences && !unloading)return;
  const batch=Array.from(discardedReferences).slice(0,128);
  if(!batch.length)return;
  const body=JSON.stringify({ids:batch});
  if(unloading && typeof navigator!=='undefined' && navigator.sendBeacon) {
    if(navigator.sendBeacon('/api/references/release',new Blob([body],{type:'application/json'}))) {
      batch.forEach(id=>discardedReferences.delete(id));return;
    }
  }
  releasingReferences=true;
  fetch('/api/references/release',{method:'POST',headers:{'Content-Type':'application/json'},body,keepalive:unloading})
    .then(response=>{if(response.ok)batch.forEach(id=>discardedReferences.delete(id));})
    .catch(()=>{}).finally(()=>{releasingReferences=false;});
}
function reconcileReferences(missing=[]) {
  if(!references.some(r=>missing.includes(r.id)))return;
  references=references.filter(r=>!missing.includes(r.id));
  renderReferences();
  showPromptNotice('Uma referência ficou indisponível. Anexe a imagem novamente.');
}

function renderReferences() {
  referencePreview.replaceChildren();
  references.forEach((reference, index) => {
    const item = document.createElement('div');
    item.className = 'reference-item';
    const image = document.createElement('img');
    image.src = reference.image;
    image.alt = `Imagem ${index + 1}: ${reference.name}`;
    const number = document.createElement('span');
    number.className = 'reference-number';
    number.textContent = String(index + 1);
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = '×';
    remove.setAttribute('aria-label', `Remover imagem ${index + 1}`);
    remove.disabled = busy;
    remove.addEventListener('click', () => {
      if (busy) return;
      references.splice(index, 1);
      releaseReferences([reference.id]);
      renderReferences();
      status.textContent = references.length ? `${references.length} referência(s) · Descreva a alteração e aperte Enter` : 'Digite sua ideia e aperte Enter';
      prompt.focus();
    });
    item.append(image, number, remove);
    referencePreview.append(item);
  });
  referencePreview.hidden = !references.length;
  prompt.placeholder = references.length ? 'Descreva a alteração que você quer…' : 'Imagine um lugar…';
}

function fillResolutions(selected = outputResolution.value) {
  outputResolution.replaceChildren();
  for (const [key,size] of Object.entries(modelCatalog.resolution_options[outputAspect.value])) outputResolution.add(new Option(`${size[0]} × ${size[1]}`,key));
  outputResolution.value = selected || '1080p';
}
outputAspect.addEventListener('change',() => fillResolutions());

function choosePreset() {
  const custom = modelProfile.value === 'custom';
  activeFamily = custom ? (customModel.profile || activeFamily) : modelProfile.value === 'default' ? 'z-image-turbo' : modelProfile.value;
  writeSd(custom ? customDraft : modelCatalog.selected.sd_defaults[modelProfile.value]);
  fillComponents(custom ? customModel : {}, !custom);
  modelStatus.textContent = '';
  setBusy();
}
function fillComponents(selected = {}, preset = false) {
  const family = activeFamily.startsWith('qwen') ? 'qwen' : activeFamily;
  for (const [key, select] of Object.entries(modelSlots)) {
    const filename = modelCatalog.model_defaults[activeFamily]?.[key];
    const expected = modelCatalog.profiles[activeFamily]?.components?.[key] || (key === 'encoder' ? 'qwen3-4b' : family);
    const paths = modelFiles.filter(path => key !== 'vision' && modelCatalog.components[path]?.role === key && modelCatalog.components[path]?.family === expected);
    paths.sort((a,b) => a.slice(a.lastIndexOf('/')+1).localeCompare(b.slice(b.lastIndexOf('/')+1),undefined,{numeric:true,sensitivity:'base'}));
    select.replaceChildren(new Option(key === 'vision' ? 'Nenhum' : 'Selecione…',''));
    for (const path of paths) {
      const option = new Option(path.slice(path.lastIndexOf('/')+1),path);
      option.title = path;
      select.add(option);
    }
    const compatible = paths.filter(path => modelCatalog.components[path]?.family === expected);
    const folder = selected.diffusion?.slice(0,selected.diffusion.lastIndexOf('/')+1);
    const match = paths.find(path => path.split('/').pop() === filename) || compatible.find(path => folder && path.startsWith(folder)) || compatible[0] || '';
    select.value = !preset && paths.includes(selected[key]) ? selected[key] : key === 'vision' && family !== 'qwen' ? '' : match;
  }
}
function fillCatalog(catalog) {
  modelCatalog = catalog;
  modelFiles = catalog.files;
  fillComponents(catalog.selected);
}
refreshModels.addEventListener('click', async () => {
  if (busy) return;
  const selection = Object.fromEntries(Object.entries(modelSlots).map(([key,input]) => [key,input.value]));
  configuring = true;
  setBusy();
  try {
    const catalog = await request('/api/models');
    modelRootPaths = catalog.roots;
    fillCatalog(catalog);
    fillComponents(selection);
    modelStatus.textContent = catalog.errors.join(' · ') || 'Arquivos atualizados.';
    await loadLibrary();
  } catch (error) { modelStatus.textContent = error.message; }
  finally { configuring = false; setBusy(); }
});
modelProfile.addEventListener('change', choosePreset);
for (const input of Object.values(modelSlots)) input.addEventListener('change',markSamplingCustom);

let libraryData = null;
let libraryChoices = {};
let libraryPollPending = false;
let libraryOperationKey = null;
let libraryRequestPending = false;
const libraryStatus = document.querySelector('#library-status');
const folderDialog = document.querySelector('#folder-dialog');
let folderMode = 'destination';
let folderLocation = null;
function byteSize(bytes) {
  return `${(Math.max(0,Number(bytes)||0)/1024**3).toLocaleString('pt-BR',{maximumFractionDigits:2})} GiB`;
}
function libraryButton(label,handler,disabled=false) {
  const button=document.createElement('button');
  button.type='button';button.textContent=label;button.disabled=disabled;
  button.addEventListener('click',handler);
  return button;
}
async function libraryAction(body) {
  if (libraryRequestPending) return;
  libraryRequestPending=true;
  libraryStatus.textContent='';
  try {
    await request('/api/library',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    await loadLibrary();
  } catch(error) {libraryStatus.textContent=error.message;}
  finally {libraryRequestPending=false;}
}
function renderLibraryProgress(data) {
  const op=data.operation || {state:'idle'};
  const active=op.state==='running';
  document.querySelector('#library-progress').hidden=!active;
  const bar=document.querySelector('#library-bar');
  if (op.phase==='verifying') bar.removeAttribute('value');
  else bar.value=op.total ? Math.min(100,op.completed/op.total*100) : 0;
  document.querySelector('#library-operation').textContent=`${op.phase==='verifying'?'Verificando':'Baixando'} · ${op.file || ''} · ${byteSize(op.completed)} / ${byteSize(op.total)}`;
  document.querySelector('#cancel-model-download').disabled=!active;
  for (const id of ['choose-destination','add-model-folder','download-all']) document.querySelector('#'+id).disabled=active || running;
  document.querySelector('#download-all').disabled ||= !data.destination || !libraryData || Object.values(libraryData.sets).every(s=>s.complete);
  if (op.state==='error') libraryStatus.textContent=op.error;
  else if(op.state==='cancelled') libraryStatus.textContent='Cancelado. O próximo download continua de onde parou.';
  else if(op.state==='done') libraryStatus.textContent=op.message || (op.action==='verify'?'Verificação concluída.':'Download concluído.');
  if (active && !libraryPollPending) {
    libraryPollPending=true;
    window.setTimeout(async()=>{
      libraryPollPending=false;
      if (!modelDialog.open) return;
      try {
        const next=await request('/api/library/progress');
        renderLibraryProgress(next);
        const key=JSON.stringify(next.operation);
        if(next.operation.state!=='running' && key!==libraryOperationKey) {libraryOperationKey=key;await loadLibrary();}
      } catch(error) {libraryStatus.textContent=error.message;}
    },900);
  }
}
async function loadLibrary() {
  try {
    const data=await request('/api/library');
    libraryData=data;
    modelsReady=!data.selection_error;
    const selection=Object.fromEntries(Object.entries(modelSlots).map(([key,input])=>[key,input.value]));
    modelRootPaths=data.roots;
    fillCatalog(data.catalog);
    fillComponents(selection);
    document.querySelector('#model-destination').textContent=data.destination ? `${data.destination}${data.free==null?'':` · ${byteSize(data.free)} livres`}` : 'Escolha a pasta para baixar os modelos.';
    const folders=document.querySelector('#library-folders');folders.replaceChildren();
    for (const path of data.roots) {
      const row=document.createElement('div');row.className='library-folder';
      const label=document.createElement('span');label.textContent=path;label.title=path;
      row.append(label,libraryButton('×',()=>libraryAction({action:'forget',folder:path}),running || data.operation.state==='running' || data.roots.length===1));
      row.querySelector('button')?.setAttribute('aria-label',`Remover pasta da biblioteca: ${path}`);
      folders.append(row);
    }
    const sets=document.querySelector('#library-sets');sets.replaceChildren();
    for (const [family,set] of Object.entries(data.sets)) {
      const card=document.createElement('article');card.className='library-card';
      const title=document.createElement('h3');title.textContent=data.catalog.profiles[family].label;
      const summary=document.createElement('p');summary.textContent=set.complete?'Disponível':`${Object.keys(set.present).length}/3 componentes · ${byteSize(set.download_bytes)} para baixar`;
      card.append(title,summary);
      const details=document.createElement('details');
      const detailsTitle=document.createElement('summary');detailsTitle.textContent='Componentes';details.append(detailsTitle);card.append(details);
      const selections={};
      for(const [role,label] of [['diffusion','Gerador'],['encoder','Encoder'],['vae','VAE']]) {
        const row=document.createElement('div');row.className='library-component';
        const caption=document.createElement('label');caption.textContent=label;caption.htmlFor=`library-${family}-${role}`;
        const select=document.createElement('select');select.id=caption.htmlFor;
        select.add(new Option('Não encontrado',''));
        for(const path of set.choices[role]) {const option=new Option(path.split('/').pop(),path);option.title=path;select.add(option);}
        const draft=libraryChoices[family]?.[role];
        select.value=set.choices[role].includes(draft) ? draft : set.present[role] || '';select.disabled=running || data.operation.state==='running';
        const location=document.createElement('small');
        const verification=document.createElement('small');
        function updateLocation() {
          location.textContent=select.value;location.title=select.value;
          const record=data.verification?.[select.value];
          verification.textContent=record ? ({official:'Padrão confirmado por SHA-256',local:'Inalterado desde a última verificação',changed:'Compatível · Conteúdo alterado desde a última verificação',unconfirmed:'Compatível · Hash de origem desconhecido',failed:'Integridade diferente do arquivo confirmado'}[record.integrity] || '') : '';
        }
        updateLocation();select.addEventListener('change',()=>{libraryChoices[family] ||= {};libraryChoices[family][role]=select.value;updateLocation();});
        selections[role]=select;row.append(caption,select,location,verification);details.append(row);
      }
      const actions=document.createElement('div');actions.className='library-toolbar';
      const unavailable=running || data.operation.state==='running';
      actions.append(libraryButton('Escolher',()=>{
        const selected=Object.fromEntries(Object.entries(selections).map(([role,input])=>[role,input.value]));
        if (Object.values(selected).some(value=>!value)) {libraryStatus.textContent='Localize ou baixe os três componentes.';return;}
        activeFamily=family;modelProfile.value=family==='z-image-turbo'?'default':family;choosePreset();fillComponents(selected);
        if (Object.entries(selected).some(([role,path])=>path.split('/').pop()!==data.catalog.model_defaults[family][role])) markSamplingCustom();
        libraryStatus.textContent=`${data.catalog.profiles[family].label} selecionado. Salve para aplicar.`;
      },unavailable || !set.complete));
      actions.append(libraryButton(set.complete?'Verificar':'Baixar / continuar',()=>{
        const components=Object.fromEntries(Object.entries(selections).map(([role,input])=>[role,input.value]));
        if(set.complete && Object.values(components).some(value=>!value)){libraryStatus.textContent='Escolha os três componentes para verificar.';return;}
        libraryAction({action:set.complete?'verify':'download',families:[family],...(set.complete?{components:{[family]:components}}:{})});
      },unavailable || (!set.complete && !data.destination)));
      if(Object.values(data.managed).some(r=>r.family===family)) actions.append(libraryButton('Remover download',()=>{
        if(window.confirm(`Remover os arquivos de ${data.catalog.profiles[family].label} baixados pelo app? Eles serão movidos para .popai-trash na pasta do modelo. Arquivos importados serão preservados.`)) libraryAction({action:'remove',family});
      },unavailable));
      card.append(actions);sets.append(card);
    }
    if(data.error)libraryStatus.textContent=data.error;
    document.querySelector('#download-all').hidden=Object.values(data.sets).every(set=>set.complete);
    document.querySelector('#download-all').textContent=`Baixar todos os conjuntos · ${byteSize(Object.values(data.sets).reduce((sum,set)=>sum+set.download_bytes,0))}`;
    renderLibraryProgress(data);
    if(data.selection_error)libraryStatus.textContent=data.selection_error;
  } catch(error) {libraryStatus.textContent=error.message;}
}
async function browseFolder(path) {
  const sequence=++folderBrowseSequence;
  document.querySelector('#folder-status').textContent='';
  document.querySelector('#folder-select').disabled=true;
  try {
    const data=await request('/api/library/folders'+(path?'?path='+encodeURIComponent(path):''));
    if(sequence!==folderBrowseSequence)return;
    folderLocation=data;
    document.querySelector('#folder-path').value=data.path;
    document.querySelector('#folder-status').textContent=`${byteSize(data.free)} livres`;
    const list=document.querySelector('#folder-list');list.replaceChildren();
    for(const folder of data.folders)list.append(libraryButton(folder.name,()=>browseFolder(folder.path)));
    document.querySelector('#folder-parent').disabled=data.path===data.parent;
    document.querySelector('#folder-select').disabled=false;
  } catch(error) {if(sequence===folderBrowseSequence)document.querySelector('#folder-status').textContent=error.message;}
}
let folderBrowseSequence=0;
async function chooseFolder(mode) {
  folderMode=mode;
  document.querySelector('#folder-title').textContent=mode==='destination'?'Pasta de download':'Localizar modelos existentes';
  folderDialog.showModal();
  await browseFolder(libraryData?.destination || undefined);
}
document.querySelector('#choose-destination').addEventListener('click',()=>chooseFolder('destination'));
document.querySelector('#add-model-folder').addEventListener('click',()=>chooseFolder('add'));
document.querySelector('#folder-parent').addEventListener('click',()=>browseFolder(folderLocation?.parent));
document.querySelector('#folder-navigation').addEventListener('submit',event=>{event.preventDefault();browseFolder(document.querySelector('#folder-path').value);});
document.querySelector('#folder-path').addEventListener('input',()=>{document.querySelector('#folder-select').disabled=true;});
document.querySelector('#folder-cancel').addEventListener('click',()=>folderDialog.close());
document.querySelector('#folder-select').addEventListener('click',async()=>{if(!folderLocation)return;folderDialog.close();await libraryAction({action:folderMode,folder:folderLocation.path});});
document.querySelector('#cancel-model-download').addEventListener('click',()=>libraryAction({action:'cancel'}));
document.querySelector('#download-all').addEventListener('click',()=>libraryAction({action:'download',families:Object.keys(libraryData.sets).filter(family=>!libraryData.sets[family].complete)}));
document.querySelector('#model-close').addEventListener('click', () => modelDialog.close());
async function openConfig(tab = 'general') {
  if (uploading || configuring || stopping) return;
  configuring = true;
  libraryChoices = {};
  setBusy();
  selectTab(tab);
  modelStatus.textContent = 'Carregando…';
  keepStatus.textContent = '';
  modelDialog.showModal();
  const hardwareRequest = request('/api/hardware').then(data => ({data}),error => ({error}));
  try {
    const catalog = await request('/api/models');
    activeFamily = catalog.selected.profile;
    fillCatalog(catalog);
    modelRootPaths = catalog.roots;
    customDraft = {...catalog.selected.sd_custom};
    customModel = {...catalog.selected.sd_custom_model};
    if (!customModel.profile) customModel = {profile:activeFamily,...Object.fromEntries(['diffusion','encoder','vae','vision'].map(key => [key,catalog.selected[key]]))};
    for (const [key, values] of [['sampler',catalog.samplers],['scheduler',catalog.schedulers]]) {
      sdInputs[key].replaceChildren();
      values.forEach(value => sdInputs[key].add(new Option(value === 'auto' ? 'Automático' : value,value)));
    }
    outputAspect.replaceChildren();
    for (const ratio of catalog.aspect_ratios) outputAspect.add(new Option(ratio,ratio));
    outputAspect.value = catalog.selected.aspect_ratio || '16:9';
    generationSize.replaceChildren();
    for (const [key,label] of Object.entries(catalog.generation_sizes)) generationSize.add(new Option(label,key));
    generationSize.value = catalog.selected.generation_size || 'standard';
    fillResolutions(catalog.selected.resolution || '1080p');
    modelProfile.value = catalog.selected.sd_profile || 'default';
    choosePreset();
    outputResolution.value = catalog.selected.resolution || '1080p';
    keepLoaded.checked = Boolean(catalog.selected.keep_loaded);
    adaptiveWeights.checked = Boolean(catalog.selected.adaptive_weights);
    modelStatus.textContent = catalog.errors.join(' · ');
    if (tab === 'models') await loadLibrary();
    for (const key of ['device','upscale_device','compatibility']) hardwareInputs[key].value = catalog.selected.hardware?.[key] || 'auto';
    try {
      const result = await hardwareRequest;
      if (result.error) throw result.error;
      const hardware = result.data;
      for (const key of ['device','upscale_device']) {
        hardwareInputs[key].replaceChildren(new Option('Automática','auto'));
        hardware.devices.filter(d => d.usable).forEach(d => hardwareInputs[key].add(new Option(`${d.index}: ${d.name}`,String(d.index))));
        hardwareInputs[key].value = catalog.selected.hardware?.[key] || 'auto';
      }
      hardwareStatus.textContent = `${hardware.selected.generator.name}`;
    } catch (error) { hardwareStatus.textContent = error.message; }
  } catch (error) { modelStatus.textContent = error.message; }
  finally { configuring = false; setBusy(); }
}
modelButton.addEventListener('click', () => openConfig());
const adjustConfig = document.querySelector('#adjust-config');
adjustConfig.addEventListener('click', () => openConfig('sd'));

keepLoaded.addEventListener('change', async () => {
  if (keepLoaded.checked) return;
  configuring = true;
  stopping = true;
  clearGenerationPreview();
  setBusy();
  keepStatus.textContent = 'Cancelando e descarregando…';
  try {
    await request('/api/cancel',{method:'POST'});
    running = false;
    clockJob = null;
    keepStatus.textContent = '';
  } catch (error) { keepStatus.textContent = error.message; }
  finally { configuring = false; stopping = false; setBusy(); }
});

cancelGeneration.addEventListener('click', async () => {
  if (stopping) return;
  stopping = true;
  clearGenerationPreview();
  setBusy();
  status.textContent = 'Cancelando…';
  try {
    await request('/api/cancel', {method:'POST'});
    running = false;
    clockJob = null;
    status.textContent = 'Pedido cancelado · Motor descarregado';
  } catch (error) { status.textContent = error.message; }
  finally { stopping = false; setBusy(); }
});

modelApply.addEventListener('click', async () => {
  if (busy) return;
  configuring = true;
  setBusy(false);
  modelStatus.textContent = 'Salvando…';
  try {
    if (modelProfile.value === 'custom') {
      customDraft = readSd();
      customModel = {profile:activeFamily,...Object.fromEntries(['diffusion','encoder','vae','vision'].map(key => [key,modelSlots[key].value]))};
    }
    const settings = {model_roots:modelRootPaths,hardware:{device:hardwareInputs.device.value,upscale_device:hardwareInputs.upscale_device.value,compatibility:hardwareInputs.compatibility.value}, profile:activeFamily, sd_custom_model:customModel, sd_profile:modelProfile.value, sd_custom:customDraft, keep_loaded:keepLoaded.checked, adaptive_weights:adaptiveWeights.checked, resolution:outputResolution.value, aspect_ratio:outputAspect.value, generation_size:generationSize.value, ...Object.fromEntries(Object.entries(modelSlots).map(([key, select]) => [key,select.value]))};
    const saved = await request('/api/models', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(settings)});
    activeFamily = saved.profile;
    modelsReady = true;
    currentFamily = activeFamily;
    modelButton.title = modelCatalog.profiles[activeFamily].label;
    status.textContent = `${modelButton.title} · ${outputResolution.selectedOptions[0].textContent} · Digite sua ideia e aperte Enter`;
    modelDialog.close();
  } catch (error) { modelStatus.textContent = error.message; }
  finally { configuring = false; setBusy(false); }
});

async function prepareReference(file) {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 20 * 1024 * 1024) {
    throw new Error('Escolha uma imagem PNG, JPG ou WebP de até 20 MB.');
  }
  const image = new Image();
  const url = URL.createObjectURL(file);
  try {
    image.src = url;
    try { await image.decode(); }
    catch { throw new Error('Não foi possível abrir essa imagem. Escolha outro arquivo.'); }
    const width = image.naturalWidth;
    const height = image.naturalHeight;
    if (!width || !height || width > 8192 || height > 8192 || width * height > 16777216) {
      throw new Error('Use uma imagem de até 8192 pixels por lado e 16 megapixels.');
    }
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    canvas.getContext('2d').drawImage(image, 0, 0);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    if (!blob || blob.size > 25 * 1024 * 1024) {
      throw new Error('A imagem ficou grande demais. Reduza seu tamanho e tente novamente.');
    }
    return blob;
  } finally {
    URL.revokeObjectURL(url);
  }
}

addReference.addEventListener('click', () => {
  if (busy || currentFamily === 'z-image-turbo') return;
  referenceFile.value = '';
  referenceFile.click();
});

referenceFile.addEventListener('change', async () => {
  const files = Array.from(referenceFile.files || []);
  if (!files.length || busy || currentFamily === 'z-image-turbo') return;
  if (references.length + files.length > 10) {
    status.textContent = 'Anexe até 10 imagens de referência. Remova uma para adicionar outra.';
    return;
  }
  uploading = true;
  setBusy(false);
  stage.classList.remove('error');
  status.textContent = 'Preparando referência…';
  try {
    for (const [index, file] of files.entries()) {
      status.textContent = `Preparando referência ${index + 1} de ${files.length}…`;
      const blob = await prepareReference(file);
      const result = await request('/api/reference', {method: 'POST', headers: {'Content-Type': 'image/png'}, body: blob});
      references.push({...result, name: file.name});
      renderReferences();
    }
    status.textContent = `${references.length} referência(s) pronta(s) · Use imagem 1, imagem 2… no pedido`;
  } catch (error) {
    stage.classList.add('error');
    status.textContent = error.message;
  } finally {
    uploading = false;
    setBusy(false);
    prompt.focus();
  }
});

async function showResult(job) {
  const epoch = previewEpoch;
  const width = job.width || 1920;
  const height = job.height || 1080;
  const image = new Image();
  image.src = job.image;
  await image.decode();
  if (epoch !== previewEpoch) return false;
  if (image.naturalWidth !== width || image.naturalHeight !== height) {
    throw new Error('O PNG final não tem as dimensões esperadas.');
  }
  image.id = 'wallpaper';
  image.alt = 'Wallpaper gerado';
  image.draggable = false;
  image.hidden = true;
  clearGenerationPreview(false);
  wallpaper.replaceWith(image);
  wallpaper = image;
  resetImageView();
  wallpaper.hidden = false;
  imageViewport.classList.add('has-image');
  imageViewSize=null;
  resizeImageView();
  welcome.hidden = true;
  save.href = job.image;
  save.download = `wallpaper-${width}x${height}.png`;
  save.setAttribute('aria-label',`Baixar imagem, ${width} por ${height} pixels`);
  save.hidden = false;
  shown = job.id;
  playCompletionSound(job.id);
  return true;
}

async function refresh() {
  try {
    if (uploading || configuring || stopping || enhancing) return;
    const heartbeat=references.length?'?references='+encodeURIComponent(references.map(r=>r.id).join(',')):'';
    const epoch = previewEpoch;
    const job = await request('/api/status'+heartbeat);
    if (epoch !== previewEpoch || uploading || configuring || stopping || enhancing) return;
    if(discardedReferences.size)releaseReferences([]);
    enhancerState=job.enhancer || {state:'stopped'};
    modelsReady=job.models_ready!==false;
    const jobKey=JSON.stringify([job.id || null,job.state]);
    if(jobKey!==observedJobKey || job.state==='running')promptNotice=null;
    observedJobKey=jobKey;
    reconcileReferences(job.missing_references);
    if (!initialStatusReceived) {
      initialStatusReceived = true;
      if (job.state === 'done') hiddenImageId = job.id;
    }
    stage.classList.remove('error');
    syncClock(job);
    renderEstimate(job);
    currentFamily = job.profile || currentFamily;
    setBusy(job.state === 'running');
    adjustConfig.hidden = !(job.config_error || job.state === 'error' && job.error_info?.action === 'settings');
    recoverableJob = job.retryable ? job.id : null;
    retryFinalize.hidden = !recoverableJob;
    if (job.config_error && job.state === 'idle') status.textContent = job.config_error;
    if (!modelDialog.open) keepLoaded.checked = Boolean(job.keep_loaded);
    if (job.state === 'running') {
      showGenerationPreview(job);
      tickClock();
    } else if (job.state === 'done' && job.id === hiddenImageId) {
      clearGenerationPreview();
      status.textContent = 'Digite sua ideia e aperte Enter';
    } else if (job.state === 'done') {
      if (shown !== job.id) {
        try {
          if (!await showResult(job)) return;
          resultError = null;
        } catch (error) {
          clearGenerationPreview();
          shown = job.id;
          resultError = 'Não foi possível abrir o PNG final. Recarregue a página para tentar novamente; a imagem permanece salva.';
          shown = null;
          save.hidden = true;
        }
      }
      if (resultError) {
        stage.classList.add('error');
        status.textContent = resultError;
      } else {
        status.textContent = `Pronto em ${formatDuration(job.elapsed)} · Digite outra ideia para criar mais`;
      }
    } else if (job.state === 'error') {
      clearGenerationPreview();
      stage.classList.add('error');
      status.textContent = job.error;
      modelButton.title = 'Ajustar configurações';
    } else if (job.state === 'cancelled') {
      clearGenerationPreview();
      status.textContent = 'Pedido cancelado · Digite outra ideia para criar mais';
    } else {
      clearGenerationPreview();
    }
    if(job.state!=='running') {
      if(job.config_error)status.textContent=job.config_error;
      else if(promptNotice?.jobKey===observedJobKey && !resultError)status.textContent=promptNotice.text;
    }
  } catch (error) {
    clearGenerationPreview();
    stage.classList.add('error');
    clockJob = null;
    timeEstimate.hidden = true;
    status.textContent = 'Sem conexão com o servidor. Tentando reconectar…';
    setBusy(true);
  } finally {
    window.setTimeout(refresh, clockJob?.phase === 'generating' ? 350 : 1500);
  }
}

function resizePrompt() {
  prompt.style.height = 'auto';
  prompt.style.height = `${prompt.scrollHeight}px`;
}
prompt.addEventListener('input',()=>{undoPrompt=null;savePromptDraft();resizePrompt();undoEnhance.hidden=true;promptNotice=null;setBusy();});
prompt.addEventListener('keydown',event => {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return;
  event.preventDefault();
  if (!busy && !event.repeat && prompt.value.trim()) form.requestSubmit();
});
window.addEventListener('resize',resizePrompt);
window.addEventListener('pagehide',event=>{if(!enhancing)savePromptDraft();if(!event?.persisted)releaseReferences(references.map(r=>r.id),true);});
window.addEventListener('pageshow',event=>{
  if(event.persisted && references.length)request('/api/status?references='+encodeURIComponent(references.map(r=>r.id).join(',')))
    .then(job=>reconcileReferences(job.missing_references)).catch(()=>{});
});
try {
  let savedState=null;
  try {savedState=JSON.parse(window.localStorage.getItem(promptStateKey));}catch {}
  const limit=prompt.maxLength>0?prompt.maxLength:16000;
  if(savedState?.version===1 && typeof savedState.text==='string') {
    prompt.value=savedState.text.slice(0,limit);
    const undo=savedState.undo;
    if(undo && typeof undo.original==='string' && undo.original.length<=limit && undo.enhanced===savedState.text && prompt.value===savedState.text)undoPrompt=undo.original;
  } else {
    const savedPrompt=window.localStorage.getItem(promptDraftKey);
    if(savedPrompt!==null)prompt.value=savedPrompt.slice(0,limit);
  }
} catch {}
resizePrompt();
updateMascot();

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (busy || !prompt.value.trim()) return;
  if(!modelsReady){await openConfig('models');return;}
  promptNotice=null;
  savePromptDraft();
  clearGenerationPreview();
  setBusy(true);
  stage.classList.remove('error');
  status.textContent = 'Iniciando…';
  try {
    await request('/api/generate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({prompt: prompt.value.trim(), reference: references.map(reference => reference.id)})});
  } catch (error) {
    setBusy(false);
    stage.classList.add('error');
    status.textContent = error.message;
    adjustConfig.hidden = false;
    prompt.focus();
  }
});

refresh();
request('/api/library').then(data=>{if(data.needs_setup)openConfig('models');}).catch(()=>{});
