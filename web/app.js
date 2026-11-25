const mascot = document.querySelector('#mascot');
let mascotState = '';
let mascotJobId=null,mascotProgress=0;
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
  const imageGenerating=Boolean(clockJob)&&!enhancing&&clockJob.phase!=='cancelling';
  const imageActive=String(imageGenerating);
  if(mascot.dataset.imageGenerating!==imageActive)mascot.dataset.imageGenerating=imageActive;
  const docked=Boolean(clockJob)||Boolean(latestImageId&&latestImageId!==hiddenImageId&&!resultError)||!wallpaper.hidden||!generationPreview.hidden;
  const placement=docked?'corner':'center';
  if(mascot.dataset.placement!==placement)mascot.dataset.placement=placement;
  if(imageGenerating){
    if(mascotJobId!==clockJob.id){mascotJobId=clockJob.id;mascotProgress=0;}
    const progress=clockJob.progress||{};
    const total=Number(progress.total)||1;
    const measured=Math.max(0,Math.min(1,(Number(progress.completed)||0)/total));
    let fraction=0;
    if(clockJob.phase==='finalizing')fraction=.99;
    else if(clockJob.phase==='upscaling'){
      const passes=Math.max(1,Number(clockJob.upscale_passes)||1);
      const pass=Math.min(passes,Math.max(1,Number(clockJob.upscale_pass)||1));
      fraction=.90+.08*(pass-1+(progress.unit==='percent'?measured:0))/passes;
    }
    else if(progress.stage==='vae_decode')fraction=.87;
    else if(progress.stage==='sampling'&&progress.unit==='steps')fraction=.85*measured;
    mascotProgress=Math.max(mascotProgress,fraction);
    fraction=mascotProgress;
    mascot.style.setProperty('--shake-distance',(0.2+4.3*Math.pow(1-fraction,1.35)).toFixed(3)+'px');
    mascot.style.setProperty('--shake-angle',(0.15+2.85*Math.pow(1-fraction,1.35)).toFixed(3)+'deg');
  }else{
    mascotJobId=null;mascotProgress=0;
    mascot.style.removeProperty('--shake-distance');
    mascot.style.removeProperty('--shake-angle');
  }
  if (mascotState === 'generating' && !generating) lastActivity = performance.now();
  const state = generating ? 'generating' : performance.now()-lastActivity >= 30000 ? 'waiting' : 'idle';
  if (state !== mascotState) {
    mascotState = state;
    mascot.dataset.state = state;
  }
}
function wakeMascot() { lastActivity = performance.now(); updateMascot(); prepareCompletionSound(); }
document.addEventListener('pointerdown',wakeMascot,{passive:true});
document.addEventListener('keydown',wakeMascot);
const form = document.querySelector('#form');
const generateImage = document.querySelector('#generate-image');
const newGeneration = document.querySelector('#new-generation');
function randomSeed() {
  return crypto.getRandomValues(new Uint32Array(1))[0] & 0x7fffffff;
}
let pageSeed = randomSeed();
const prompt = document.querySelector('#prompt');
const promptDraftKey = 'popai.prompt-draft';
const promptStateKey = 'popai.prompt-state';
const composerSessionKey = 'popai.composer-session';
const assetId = /^[a-f0-9]{32}$/;
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
    clearResult();
    welcome.hidden = true;
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
const drawReference = document.querySelector('#draw-reference');
const sketchDialog = document.querySelector('#sketch-dialog');
const sketchFrame = document.querySelector('#sketch-frame');
const referenceFile = document.querySelector('#reference-file');
const referencePreview = document.querySelector('#reference-preview');
const referenceDialog = document.querySelector('#reference-dialog');
const referenceLarge = document.querySelector('#reference-large');
const referenceClose = document.querySelector('#reference-close');
const modelButton = document.querySelector('#model-button');
const hideComposer = document.querySelector('#hide-composer');
const modelDialog = document.querySelector('#model-dialog');
const modelProfile = document.querySelector('#model-profile');
const profileList = document.querySelector('#profile-list');
const profileCards = [...profileList.querySelectorAll('.profile-card')];
const profilePresetLabels = [...profileList.querySelectorAll('.profile-preset')];
const profileCustomButton = document.querySelector('#profile-custom');
const profileMode = document.querySelector('#profile-mode');
let expandedProfileFamily = null;
const modelStatus = document.querySelector('#model-status');
const modelApply = document.querySelector('#model-apply');
const outputAspect = document.querySelector('#output-aspect');
const generationSize = document.querySelector('#generation-size');
const outputResolution = document.querySelector('#output-resolution');
const adaptiveWeights = document.querySelector('#adaptive-weights');
const preloadModel = document.querySelector('#preload-model');
const processingCard=document.querySelector('#prompt-processing-card');
const processingToggle=document.querySelector('#prompt-processing-toggle');
const processingOptions=document.querySelector('#prompt-processing-options');
const processingSummary=document.querySelector('#prompt-processing-summary');
const processingInputs={corrector:document.querySelector('#prompt-corrector-enabled'),enhancer:document.querySelector('#prompt-enhancer-enabled'),lite:document.querySelector('#prompt-lite-enabled')};
const processingDefaults={corrector:true,enhancer:true,lite:false};
let processingSettings={...processingDefaults};
let processingSupported=false;
const processingRestartNotice='Restart popAI to activate prompt processing settings.';
function acceptProcessingSettings(options){
  processingSupported=!!options&&Object.keys(processingDefaults).every(key=>typeof options[key]==='boolean');
  if(processingSupported)processingSettings={...options};
}
function allowedPromptMode(mode){
  if(!processingSupported)return false;
  return processingSettings.enhancer?['simple','detailed','creative','cinematic'].includes(mode):processingSettings.corrector&&mode==='corrector';
}
function processingDraft(){return Object.fromEntries(Object.entries(processingInputs).map(([key,input])=>[key,Boolean(input.checked)]));}
function refreshProcessingSummary(){
  const draft=processingDraft();
  processingSummary.textContent=!draft.corrector&&!draft.enhancer?'Off':draft.lite?'Lite':'Normal';
}
function fillProcessingSettings(options){
  const values={...processingDefaults,...options};
  for(const [key,input] of Object.entries(processingInputs))input.checked=values[key];
  refreshProcessingSummary();
}
processingToggle.addEventListener('click',()=>{
  const expanded=processingOptions.hidden;
  processingOptions.hidden=!expanded;
  processingCard.classList.toggle('is-expanded',expanded);
  processingToggle.setAttribute('aria-expanded',String(expanded));
});
for(const input of Object.values(processingInputs))input.addEventListener('change',refreshProcessingSummary);
const timeEstimate = document.querySelector('#time-estimate');
const estimateArc = document.querySelector('#eta-arc');
const estimateMessage = document.querySelector('#estimate-message');
function generationPhaseLabel(job) {
  if (job.phase === 'cancelling') return 'Canceling';
  if (job.phase === 'upscaling') return 'Upscaling';
  if (job.phase === 'finalizing') return 'Finalizing PNG';
  const progress = job.progress || {};
  if (progress.stage === 'vae_decode') return 'Decoding image';
  if (progress.stage === 'sampling') {
    return progress.total > 0 && progress.completed >= progress.total ? 'Finalizing base image' : 'Generating image';
  }
  return 'Preparing generation';
}

function renderEstimate(job) {
  const hidden = job.state !== 'running' || job.phase === 'cancelling';
  if (timeEstimate.hidden !== hidden) timeEstimate.hidden = hidden;
  if (hidden) return;
  const progress = job.progress || {};
  const total = Number(progress.total);
  const completed = Number(progress.completed);
  const sampling = job.phase === 'generating' && progress.stage === 'sampling' && progress.unit === 'steps' && total > 0;
  const remaining = Number(progress.remaining_seconds);
  const estimate = remaining > 0 && Number.isFinite(remaining) ? ` · ≈ ${formatDuration(remaining)} remaining` : '';
  const upscaling = job.phase === 'upscaling' && job.upscale_passes !== 2 && progress.unit === 'percent' && total > 0;
  const measured = sampling || upscaling;
  estimateArc.hidden = !measured;
  estimateArc.setAttribute('stroke-dashoffset',String(measured ? 100*(1-Math.min(completed/total,1)) : 100));
  let message = generationPhaseLabel(job);
  if (sampling) message = `${completed}/${total} steps${completed >= total ? ` · ${message}` : estimate}`;
  if (upscaling) message = `${Math.floor(completed)}%${completed >= total ? ' · Finalizing upscale' : estimate || ` · ${message}`}`;
  if (estimateMessage.textContent !== message) {
    estimateMessage.textContent = message;
    timeEstimate.setAttribute('aria-label', message);
  }
}
let clockJob = null;
let clockAnchor = 0;
let clockElapsed = 0;
function syncClock(job) {
  if (job.state !== 'running') {
    clockJob = null;
    renderEstimate(job);
    updateMascot();
    return;
  }
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
  const message = `${generationPhaseLabel(clockJob)} · Total ${formatDuration(Math.floor(clockElapsed+delta))}`;
  if (status.textContent !== message) status.textContent = message;
  const progress = {...clockJob.progress};
  if (progress.remaining_seconds != null) progress.remaining_seconds = Math.max(0,progress.remaining_seconds-delta);
  renderEstimate({...clockJob,progress});
}
window.setInterval(tickClock,200);
const cancelGeneration = document.querySelector('#cancel-generation');
const modelSlots = Object.fromEntries(['diffusion', 'encoder', 'vae', 'vision'].map(key => [key, document.querySelector(`#model-${key}`)]));
let modelRootPaths = [];
const refreshModels = document.querySelector('#refresh-models');
let modelFiles = [];
let modelCatalog = null;
let customDraft = null;
let customModel = {};
let activeFamily = 'z-image-turbo';
let currentFamily = 'z-image-turbo';
const sdInputs = Object.fromEntries(['steps','cfg','sampler','scheduler','vae_tiling','vae_tile_size','mmap'].map(key => [key,document.querySelector('#sd-' + key.replaceAll('_','-'))]));
const configScroll = document.querySelector('.config-scroll');
const configTabs = ['general', 'sd', 'models'].map(name => ({
  name,
  button: document.querySelector('#tab-' + name),
  panel: document.querySelector('#panel-' + name),
}));
let selectedConfigTab = 0;
function selectTab(name) {
  const next = configTabs.findIndex(tab => tab.name === name);
  if (modelDialog.open && next === selectedConfigTab) return false;
  const direction = !modelDialog.open ? '' : next > selectedConfigTab ? 'forward' : 'backward';
  configTabs[next].panel.setAttribute('data-slide', direction);
  for (const tab of configTabs) {
    const selected = tab.name === name;
    tab.panel.hidden = !selected;
    tab.button.setAttribute('aria-selected', String(selected));
  }
  selectedConfigTab = next;
  configScroll.scrollTop = 0;
  return true;
}
for (const {name, button} of configTabs) {
  button.addEventListener('click', () => {
    const changed = selectTab(name);
    if (name === 'models') loadLibrary(changed);
  });
}
function readSd() {
  return Object.fromEntries(Object.entries(sdInputs).map(([key,input]) => [key, ['vae_tiling','mmap'].includes(key) ? input.checked : ['steps','cfg','vae_tile_size'].includes(key) ? Number(input.value) : input.value]));
}
function writeSd(value) {
  for (const [key,input] of Object.entries(sdInputs)) {
    if (['vae_tiling','mmap'].includes(key)) input.checked = value[key];
    else input.value = value[key];
  }
}
function renderProfilePicker() {
  const custom = modelProfile.value === 'custom';
  for (const card of profileCards) {
    const family = card.dataset.family;
    const expanded = family === expandedProfileFamily;
    const selected = family === activeFamily;
    card.classList.toggle('is-expanded', expanded);
    card.classList.toggle('is-selected', selected);
    card.querySelector('.profile-card-toggle').setAttribute('aria-expanded', String(expanded));
    card.querySelector('.profile-variants').hidden = !expanded;
    card.querySelector('.profile-current-marker').hidden = !selected;
    if (selected) card.querySelector('.profile-card-steps').textContent = `${sdInputs.steps.value} steps`;
    else {
      const first = card.querySelector('.profile-preset span').textContent.match(/\d+ steps/);
      if (first) card.querySelector('.profile-card-steps').textContent = first[0];
    }
  }
  for (const label of profilePresetLabels) {
    const checked = !custom && label.dataset.profile === modelProfile.value;
    label.classList.toggle('is-selected', checked);
    label.querySelector('input').checked = checked;
  }
  profileCustomButton.textContent = custom ? 'Custom active ✓' : 'Edit manually ↗';
  profileMode.textContent = custom ? 'Custom settings' : `${sdInputs.steps.value} steps · ${profilePresetLabels.find(label => label.dataset.profile === modelProfile.value)?.querySelector('small') ? 'Default' : 'Preset'}`;
}

for (const card of profileCards) {
  card.querySelector('.profile-card-toggle').addEventListener('click', () => {
    if (busy) return;
    expandedProfileFamily = expandedProfileFamily === card.dataset.family ? null : card.dataset.family;
    renderProfilePicker();
  });
}
for (const label of profilePresetLabels) {
  label.querySelector('input').addEventListener('change', () => {
    if (busy) return;
    modelProfile.value = label.dataset.profile;
    choosePreset();
  });
}
profileCustomButton.addEventListener('click', () => {
  if (busy) return;
  markSamplingCustom();
  sdInputs.steps.focus();
});
function markSamplingCustom() {
  customDraft = readSd();
  customModel = {profile:activeFamily,...Object.fromEntries(['diffusion','encoder','vae','vision'].map(key => [key,modelSlots[key].value]))};
  modelProfile.value = 'custom';
  modelStatus.textContent = '';
  renderProfilePicker();
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
const enhanceControl = document.querySelector('#enhance-control');
const enhanceOptions = document.querySelector('#enhance-options');
const cancelEnhance = document.querySelector('#cancel-enhance');
const undoEnhance = document.querySelector('#undo-enhance');
let references = [];
let shown = null;
let initialStatusReceived = false;
let hiddenImageId = null;
let latestImageId = null;
let currentJobId = null;
let discardJobId = null;
let rememberedResult = null;
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
  if (!response.ok) throw new Error(body.error || 'Could not reach the server.');
  return body;
}

function canImprovePrompt() {
  return !busy && processingSupported && (processingSettings.corrector||processingSettings.enhancer) && ['ready','error','stopped'].includes(enhancerState.state) && !enhancerState.busy && !!prompt.value.trim();
}

function setBusy(value = running) {
  running = value;
  busy = value || uploading || configuring || enhancing;
  newGeneration.disabled = busy || stopping;
  generateImage.disabled = newGeneration.disabled || !prompt.value.trim();
  refreshModels.disabled = busy;
  Object.values(sdInputs).forEach(input => { input.disabled = busy; });
  adjustConfig.disabled = busy;
  retryFinalize.disabled = busy;
  prompt.disabled = busy;
  addReference.disabled = busy || currentFamily === 'z-image-turbo';
  drawReference.hidden = currentFamily === 'z-image-turbo';
  drawReference.disabled = busy || !modelsReady || references.length >= 10;
  addReference.hidden = false;
  addReference.title = currentFamily !== 'z-image-turbo' ? 'Add reference image' : 'Reference images are unavailable for this model';
  referencePreview.querySelectorAll('button').forEach(button => { button.disabled = busy; });
  modelButton.disabled = uploading || configuring || stopping || enhancing;
  modelApply.disabled = busy || !processingSupported;
  processingToggle.disabled=busy || !processingSupported;
  for(const input of Object.values(processingInputs))input.disabled=busy || !processingSupported;
  modelProfile.disabled = busy;
  preloadModel.disabled = busy;
  for (const card of profileCards) card.querySelector('.profile-card-toggle').disabled = busy;
  for (const label of profilePresetLabels) label.querySelector('input').disabled = busy;
  profileCustomButton.disabled = busy;
  outputResolution.disabled = busy;
  outputAspect.disabled = busy;
  generationSize.disabled = busy;
  Object.values(modelSlots).forEach(select => { select.disabled = busy; });
  cancelGeneration.hidden = !running;
  cancelGeneration.disabled = stopping;
  stage.classList.toggle('busy', busy);
  form.setAttribute('aria-busy', String(busy));
  enhanceControl.hidden = busy || ((!processingSupported||!processingSettings.corrector&&!processingSettings.enhancer)&&undoPrompt===null);
  const canImprove = canImprovePrompt();
  const canUndo = !busy && undoPrompt !== null;
  undoEnhance.hidden = !canUndo;
  undoEnhance.disabled = !canUndo;
  for(const option of enhanceOptions.querySelectorAll('button[data-mode]')){
    option.hidden=!processingSupported||!processingSettings.enhancer;
    option.disabled=!canImprove||option.hidden;
  }
  enhancePrompt.disabled = !canImprove && !canUndo;
  if(enhancePrompt.disabled||(!processingSettings.enhancer&&!canUndo))setEnhanceOptions(false);
  const correctOnly=allowedPromptMode('corrector');
  const action=!canImprove&&canUndo?'Undo prompt enhancement':correctOnly?'Correct prompt':'Enhance prompt';
  enhancePrompt.title=action;
  enhancePrompt.setAttribute('aria-label',action);
  enhancePrompt.classList.toggle('enhancing',enhancing);
  enhancePrompt.setAttribute('aria-busy',String(enhancing));
  cancelEnhance.hidden = !enhancing;
}

function setEnhanceOptions(open) {
  const visible = open && !enhancePrompt.disabled && ((processingSupported && processingSettings.enhancer && canImprovePrompt()) || !undoEnhance.hidden);
  enhanceOptions.hidden = !visible;
  enhancePrompt.setAttribute('aria-expanded', String(visible));
}

enhanceControl.addEventListener('pointerenter', event => {
  if (event.pointerType !== 'touch') setEnhanceOptions(true);
});
enhanceControl.addEventListener('pointerleave', () => {
  if (!enhanceOptions.contains(document.activeElement)) setEnhanceOptions(false);
});
enhanceControl.addEventListener('focusout', event => {
  if (!enhanceControl.contains(event.relatedTarget)) setEnhanceOptions(false);
});
enhanceControl.addEventListener('keydown', event => {
  if (event.key !== 'Escape' || enhanceOptions.hidden) return;
  event.preventDefault();
  setEnhanceOptions(false);
  enhancePrompt.focus();
});
document.addEventListener('pointerdown', event => {
  if (!enhanceOptions.hidden && !enhanceControl.contains(event.target)) setEnhanceOptions(false);
});
enhancePrompt.addEventListener('click', () => {
  if (enhancePrompt.disabled) return;
  if (allowedPromptMode('corrector') && canImprovePrompt()) {
    setEnhanceOptions(false);
    return improvePrompt('corrector');
  }
  setEnhanceOptions(true);
  if (!enhanceOptions.hidden) enhanceOptions.querySelector('button:not([hidden]):not(:disabled)')?.focus();
});
enhanceOptions.addEventListener('click', event => {
  const option = event.target.closest('button[data-mode]');
  if (option && !option.hidden && !option.disabled && allowedPromptMode(option.dataset.mode)) improvePrompt(option.dataset.mode);
});

const thoughtPopup=document.querySelector('#thought-popup');
const thoughtBody=document.querySelector('#thought-body');
const thoughtToggle=document.querySelector('#thought-toggle');
const thoughtSections=Object.fromEntries([...thoughtPopup.querySelectorAll('.thought-section')].map(el=>[el.dataset.phase,el]));
const thoughtEyes={
  corrector:mascot.querySelector('.eye-corrector'),
  enhancer:mascot.querySelector('.eye-enhancer')
};
let thoughtPhase='idle',thoughtMinimized=false,thoughtAnimation=null;
let thoughtDisplayPhase='idle',thoughtHoldTimer=null,thoughtHoldUntil=0;
function clearThoughtHold(){
  if(thoughtHoldTimer!==null)window.clearTimeout(thoughtHoldTimer);
  thoughtHoldTimer=null;thoughtHoldUntil=0;
}
function hasThoughtContent(phase){
  const el=thoughtSections[phase];
  return !!el&&(Boolean((el.querySelector('.thought-text').textContent||'').trim())||
    Boolean((el.querySelector('.thought-answer-text').textContent||'').trim()));
}
function displayThought(phase){
  thoughtDisplayPhase=phase;
  for(const [key,el] of Object.entries(thoughtSections))el.dataset.active=String(key===phase);
  thoughtPopup.hidden=thoughtMinimized||!hasThoughtContent(phase);
}
function holdThought(next,delay=3000,after=null){
  clearThoughtHold();
  thoughtHoldUntil=performance.now()+delay;
  thoughtHoldTimer=window.setTimeout(()=>{
    thoughtHoldTimer=null;thoughtHoldUntil=0;
    displayThought(next);
    if(after)after();
  },delay);
}
function revealThought(phase){
  if(phase===thoughtDisplayPhase&&!thoughtMinimized&&!thoughtAnimation&&hasThoughtContent(phase))thoughtPopup.hidden=false;
}
function finishThoughts(success){
  const previous=thoughtPhase,displayed=thoughtDisplayPhase;
  const remaining=Math.max(0,thoughtHoldUntil-performance.now());
  clearThoughtHold();
  stopThoughtAnimation();
  setMascotPhase('idle');
  if(success&&!thoughtMinimized&&hasThoughtContent(previous)){
    if(displayed!==previous&&hasThoughtContent(displayed)&&remaining>0){
      displayThought(displayed);
      holdThought(previous,remaining,()=>holdThought('idle'));
    }else{
      displayThought(previous);
      holdThought('idle');
    }
  }else displayThought('idle');
  thoughtMinimized=false;
  syncThoughtEyes();
}
function stopThoughtAnimation(){
  const anim=thoughtAnimation;
  thoughtAnimation=null;
  if(anim)anim.cancel();
  delete thoughtPopup.dataset.transitioning;
}
function syncThoughtEyes(){
  for(const [key,eye] of Object.entries(thoughtEyes)){
    const docked=thoughtMinimized&&thoughtPhase===key;
    eye.dataset.docked=String(docked);
    eye.disabled=!docked;
    eye.setAttribute('aria-expanded',String(thoughtPhase===key&&!thoughtMinimized));
  }
}
function resetThoughts(){
  clearThoughtHold();
  stopThoughtAnimation();
  thoughtMinimized=false;
  thoughtPhase='idle';thoughtDisplayPhase='idle';
  thoughtBody.hidden=false;
  thoughtToggle.textContent='−';
  thoughtToggle.setAttribute('aria-expanded','true');
  thoughtToggle.setAttribute('aria-label','Minimize processing');
  for(const el of Object.values(thoughtSections)){
    el.querySelector('.thought-text').textContent='';
    el.querySelector('.thought-answer').hidden=true;
    el.querySelector('.thought-answer-text').textContent='';
    el.querySelector('.thought-scroll').scrollTop=0;
    el.querySelector('.thought-state').textContent='Waiting';
    el.dataset.active='false';
  }
  thoughtPopup.hidden=true;
  syncThoughtEyes();
}
function animateThoughtDock(hide){
  if(thoughtPhase==='idle'){if(hide){clearThoughtHold();displayThought('idle');}return;}
  if(thoughtMinimized===hide)return;
  if(!hide&&!hasThoughtContent(thoughtPhase)){
    thoughtMinimized=false;displayThought(thoughtPhase);syncThoughtEyes();thoughtToggle.setAttribute('aria-expanded','true');return;
  }
  if(hide){clearThoughtHold();thoughtDisplayPhase=thoughtPhase;}
  else displayThought(thoughtPhase);
  const eye=thoughtEyes[thoughtPhase];
  stopThoughtAnimation();
  thoughtMinimized=hide;
  thoughtPopup.hidden=false;
  if(!hide){
    const scroll=thoughtSections[thoughtPhase].querySelector('.thought-scroll');
    scroll.scrollTop=scroll.scrollHeight;
  }
  const r=thoughtPopup.getBoundingClientRect(),e=eye.getBoundingClientRect();
  const dx=e.left+e.width/2-r.left-r.width/2,dy=e.top+e.height/2-r.top-r.height/2;
  const scale=Math.min(e.width/Math.max(1,r.width),e.height/Math.max(1,r.height))*.8;
  const expanded={transform:'translate(0px,0px) scale(1)',opacity:1};
  const docked={transform:'translate('+dx+'px,'+dy+'px) scale('+scale+')',opacity:0};
  syncThoughtEyes();
  thoughtToggle.setAttribute('aria-expanded',String(!hide));
  if(matchMedia('(prefers-reduced-motion: reduce)').matches||!thoughtPopup.animate){
    thoughtPopup.hidden=hide;
    if(hide)displayThought(thoughtPhase);
    if(hide)eye.focus({preventScroll:true});else thoughtToggle.focus({preventScroll:true});
    return;
  }
  thoughtPopup.dataset.transitioning='true';
  const anim=thoughtPopup.animate(hide?[expanded,docked]:[docked,expanded],{duration:280,easing:'cubic-bezier(.22,.8,.24,1)',fill:'both'});
  thoughtAnimation=anim;
  anim.finished.then(()=>{
    if(thoughtAnimation!==anim)return;
    thoughtPopup.hidden=hide;
    stopThoughtAnimation();
    if(hide)displayThought(thoughtPhase);
    if(hide&&thoughtPhase!=='idle')thoughtEyes[thoughtPhase].focus({preventScroll:true});
    else if(!hide)thoughtToggle.focus({preventScroll:true});
  }).catch(()=>{});
}
thoughtToggle.addEventListener('click',()=>animateThoughtDock(true));
for(const [key,eye] of Object.entries(thoughtEyes)){
  eye.addEventListener('click',()=>{if(thoughtMinimized&&thoughtPhase===key)animateThoughtDock(false);});
}
function appendThought(phase,text){
  const el=thoughtSections[phase];
  if(!el)return;
  const scroll=el.querySelector('.thought-scroll');
  const follow=scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<24;
  el.querySelector('.thought-text').textContent+=text;
  revealThought(phase);
  if(follow)scroll.scrollTop=scroll.scrollHeight;
}
function appendAnswer(phase,text){
  const el=thoughtSections[phase];
  if(!el)return;
  const scroll=el.querySelector('.thought-scroll');
  const follow=scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<24;
  el.querySelector('.thought-answer').hidden=false;
  el.querySelector('.thought-answer-text').textContent+=text;
  el.querySelector('.thought-state').textContent='Responding';
  revealThought(phase);
  if(follow)scroll.scrollTop=scroll.scrollHeight;
}
function setMascotPhase(phase){
  mascot.dataset.corrector=phase==='corrector'?'active':'idle';
  mascot.dataset.enhancer=phase==='enhancer'?'active':'idle';
  for(const [key,el] of Object.entries(thoughtSections)){
    el.querySelector('.thought-state').textContent=key===phase?'Processing':phase==='enhancer'&&key==='corrector'&&processingSettings.corrector?'Done':'Waiting';
  }
  if(phase!==thoughtPhase){
    const previous=thoughtPhase;
    const wasAnimating=Boolean(thoughtAnimation);
    stopThoughtAnimation();
    thoughtPhase=phase;
    if(phase==='idle'){
      displayThought('idle');
    }else if(previous!=='idle'&&!thoughtMinimized&&!thoughtPopup.hidden&&hasThoughtContent(thoughtDisplayPhase)){
      holdThought(phase);
    }else{
      clearThoughtHold();
      displayThought(phase);
    }
    if(wasAnimating&&!thoughtMinimized&&!thoughtPopup.hidden)thoughtToggle.focus({preventScroll:true});
  }
  syncThoughtEyes();
}

async function improvePrompt(mode) {
  if (!canImprovePrompt() || !allowedPromptMode(mode)) return;
  const original=prompt.value;
  const originalUndo=undoPrompt;
  savePromptDraft();
  let text='',pending='',done=false,seconds=0,success=false;
  undoPrompt=null;undoEnhance.hidden=true;
  promptNotice=null;
  enhancing=true;enhanceController=new AbortController();setBusy();updateMascot();
  status.textContent=processingSettings.corrector?'Correcting prompt…':'Enhancing prompt…';resetThoughts();setMascotPhase(processingSettings.corrector?'corrector':'enhancer');stage.classList.remove('error');
  try {
    const response=await fetch('/api/enhance',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:original,editing:references.length>0,mode}),signal:enhanceController.signal});
    if(!response.ok) {const error=await response.json();throw new Error(error.error || 'Could not enhance the prompt.');}
    if(!response.body)throw new Error('The browser did not receive the enhanced prompt.');
    const reader=response.body.getReader(),decoder=new TextDecoder();
    function receive(line) {
      if(!line.trim())return;
      const event=JSON.parse(line);
      if(event.error)throw new Error(event.error);
      if(event.stage==='corrector'||event.stage==='enhancer'){
        setMascotPhase(event.stage);
        status.textContent=event.stage==='corrector'?'Correcting prompt…':'Enhancing prompt…';
      }
      if(event.phase===thoughtPhase&&typeof event.thought==='string')appendThought(event.phase,event.thought);
      if(event.phase===thoughtPhase&&typeof event.answer==='string')appendAnswer(event.phase,event.answer);
      if(event.text) text+=event.text;
      if(event.state==='done') {done=true;seconds=event.seconds;}
    }
    while(true) {
      const chunk=await reader.read();
      if(chunk.done){pending+=decoder.decode();if(pending.trim())receive(pending);break;}
      pending+=decoder.decode(chunk.value,{stream:true});
      const lines=pending.split('\n');pending=lines.pop();lines.forEach(receive);
    }
    if(!done || !text.trim())throw new Error('Prompt enhancement was interrupted. The original text was restored.');
    prompt.value=text.trim();undoPrompt=original;success=true;
    showPromptNotice(`Prompt ${processingSettings.enhancer?'enhanced':'corrected'} · ${seconds.toLocaleString('en-US')}s`);
  } catch(error) {
    enhanceController.abort();prompt.value=original;undoPrompt=originalUndo;
    showPromptNotice(error.name==='AbortError'?'Enhancement canceled · Original text restored':error.message);
  } finally {
    finishThoughts(success);enhancing=false;enhanceController=null;savePromptDraft();resizePrompt();setBusy();updateMascot();prompt.focus();
  }
}
cancelEnhance.addEventListener('click',()=>{
  enhanceController?.abort();
  request('/api/enhance/cancel',{method:'POST'}).catch(()=>{});
});
undoEnhance.addEventListener('click',()=>{
  if(busy || undoPrompt===null)return;
  setEnhanceOptions(false);
  prompt.value=undoPrompt;undoPrompt=null;undoEnhance.hidden=true;savePromptDraft();resizePrompt();setBusy();prompt.focus();showPromptNotice('Original text restored');
});

function validSketchState(state) {
  if (!state || state.version !== 1 || !Array.isArray(state.items) || state.items.length > 1500) return false;
  if (state.base != null && (typeof state.base !== 'string' ||
      state.base.length > 1600000 || !/^data:image\/png;base64,[a-zA-Z0-9+/=]+$/.test(state.base))) return false;
  try { return JSON.stringify(state).length <= 2000000; } catch { return false; }
}
function generationPrompt(text, attached){
  const instructions=[];
  attached.forEach((reference,index)=>{
    if(!validSketchState(reference.sketch))return;
    const image='image '+(index+1);
    if(reference.sketch.items.some(item=>item.kind==='pose')){
      instructions.push('Use '+image+' only as a guide for body poses, relative positions and composition. Render the characters described in the text, not the mannequin, construction lines, colors or sketch style.');
    }else{
      instructions.push('Use '+image+' as a guide for spatial layout and composition. Render the scene described in the text, rather than reproducing the sketch style or guide marks.');
    }
  });
  return instructions.length?text+'\n\n'+instructions.join(' '):text;
}
function isSketchReference(reference) {
  return !!reference.sketch || reference.name === 'Sketch 4:3';
}
function openReferencePreview(reference) {
  referenceLarge.src = reference.image;
  referenceLarge.alt = reference.name;
  referenceDialog.showModal();
}
referenceClose.addEventListener('click', () => referenceDialog.close());
referenceDialog.addEventListener('click', event => {
  if (event.target === referenceDialog) referenceDialog.close();
});
referenceDialog.addEventListener('close', () => {
  referenceLarge.removeAttribute('src');
});
const discardedReferences=new Set();
let releasingReferences=false;
function releaseReferences(ids) {
  ids.forEach(id=>discardedReferences.add(id));
  if(releasingReferences)return;
  const batch=Array.from(discardedReferences).slice(0,128);
  if(!batch.length)return;
  const body=JSON.stringify({ids:batch});
  releasingReferences=true;
  fetch('/api/references/release',{method:'POST',headers:{'Content-Type':'application/json'},body})
    .then(response=>{if(response.ok)batch.forEach(id=>discardedReferences.delete(id));})
    .catch(()=>{}).finally(()=>{releasingReferences=false;});
}
function reconcileReferences(missing=[]) {
  if(!references.some(r=>missing.includes(r.id)))return;
  references=references.filter(r=>!missing.includes(r.id));
  renderReferences();
  showPromptNotice('A reference image is unavailable. Attach it again.');
}

function renderReferences() {
  referencePreview.replaceChildren();
  references.forEach((reference, index) => {
    const item = document.createElement('div');
    item.className = 'reference-item';
    const open = document.createElement('button');
    open.type = 'button';
    open.className = 'reference-open';
    open.setAttribute('aria-label', isSketchReference(reference) ? `Edit sketch ${index + 1}` : `Preview image ${index + 1}`);
    open.title = isSketchReference(reference) ? 'Edit drawing' : 'Preview image';
    if (isSketchReference(reference)) open.dataset.sketch = 'true';
    const image = document.createElement('img');
    image.src = reference.image;
    image.alt = `Image ${index + 1}: ${reference.name}`;
    open.append(image);
    open.addEventListener('click', () => {
      if (isSketchReference(reference) && !busy && currentFamily !== 'z-image-turbo') openSketch(reference);
      else openReferencePreview(reference);
    });
    const number = document.createElement('span');
    number.className = 'reference-number';
    number.textContent = String(index + 1);
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = '×';
    remove.setAttribute('aria-label', `Remove image ${index + 1}`);
    remove.disabled = busy;
    remove.addEventListener('click', () => {
      if (busy) return;
      references.splice(index, 1);
      releaseReferences([reference.id]);
      renderReferences();
      status.textContent = references.length ? `${references.length} attached · Describe the edit and press Enter` : 'Enter a prompt and press Enter';
      prompt.focus();
    });
    item.append(open, number, remove);
    referencePreview.append(item);
  });
  referencePreview.hidden = !references.length;
  drawReference.disabled = busy || !modelsReady || references.length >= 10;
  prompt.placeholder = references.length ? 'Describe the edit you want…' : 'Describe your image…';
  saveComposerSession();
}

function saveComposerSession() {
  try {
    window.sessionStorage.setItem(composerSessionKey, JSON.stringify({
      references: references.map(({id, name, sketch}) => ({id, name, ...(sketch && validSketchState(sketch) ? {sketch} : {})})),
      hiddenImageId,
      result: rememberedResult,
    }));
  } catch {}
}

function restoreComposerSession() {
  try {
    const saved = JSON.parse(window.sessionStorage.getItem(composerSessionKey));
    if (!saved) return;
    if (Array.isArray(saved.references)) {
      references = saved.references
        .filter(item => typeof item?.id === 'string' && assetId.test(item.id) && typeof item.name === 'string')
        .slice(0, 10)
        .map(({id, name, sketch}) => ({id, name, image: `/references/${id}.png`, ...(validSketchState(sketch) ? {sketch} : {})}));
    }
    if (typeof saved.hiddenImageId === 'string' && assetId.test(saved.hiddenImageId)) hiddenImageId = saved.hiddenImageId;
    const result = saved.result;
    if (typeof result?.id === 'string' && assetId.test(result.id) && result.id !== hiddenImageId &&
        Number.isInteger(result.width) && result.width > 0 && Number.isInteger(result.height) && result.height > 0) {
      rememberedResult = {id: result.id, width: result.width, height: result.height};
    }
  } catch {}
  renderReferences();
}

function fillResolutions(selected = outputResolution.value) {
  outputResolution.replaceChildren();
  for (const [key,size] of Object.entries(modelCatalog.resolution_options[outputAspect.value])) outputResolution.add(new Option(`${size[0]} × ${size[1]}`,key));
  outputResolution.value = selected || '1080p';
}
outputAspect.addEventListener('change',() => fillResolutions());

function choosePreset() {
  const custom = modelProfile.value === 'custom';
  activeFamily = custom ? (customModel.profile || activeFamily) : modelCatalog.sd_profile_families[modelProfile.value];
  writeSd(custom ? customDraft : modelCatalog.selected.sd_defaults[modelProfile.value]);
  fillComponents(custom ? customModel : {}, !custom);
  expandedProfileFamily = activeFamily;
  modelStatus.textContent = '';
  setBusy();
  renderProfilePicker();
}
function fillComponents(selected = {}, preset = false) {
  const family = modelCatalog.profiles[activeFamily]?.family || activeFamily;
  for (const [key, select] of Object.entries(modelSlots)) {
    const filename = modelCatalog.profile_files[activeFamily]?.[key];
    const expected = modelCatalog.profiles[activeFamily]?.components?.[key] || (key === 'encoder' ? 'qwen3-4b' : family);
    const paths = modelFiles.filter(path => (key !== 'vision' || modelCatalog.profiles[activeFamily]?.components?.vision) && modelCatalog.components[path]?.role === key && modelCatalog.components[path]?.family === expected);
    paths.sort((a,b) => a.slice(a.lastIndexOf('/')+1).localeCompare(b.slice(b.lastIndexOf('/')+1),undefined,{numeric:true,sensitivity:'base'}));
    select.replaceChildren(new Option(key === 'vision' ? 'None' : 'Select…',''));
    for (const path of paths) {
      const option = new Option(path.slice(path.lastIndexOf('/')+1),path);
      option.title = path;
      select.add(option);
    }
    const compatible = paths.filter(path => modelCatalog.components[path]?.family === expected);
    const folder = selected.diffusion?.slice(0,selected.diffusion.lastIndexOf('/')+1);
    const match = paths.find(path => path.split('/').pop() === filename) || compatible.find(path => folder && path.startsWith(folder)) || compatible[0] || '';
    select.value = !preset && paths.includes(selected[key]) ? selected[key] : key === 'vision' && !modelCatalog.profiles[activeFamily]?.components?.vision ? '' : match;
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
    modelStatus.textContent = catalog.errors.join(' · ') || 'Files refreshed.';
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
  return `${(Math.max(0,Number(bytes)||0)/1024**3).toLocaleString('en-US',{maximumFractionDigits:2})} GiB`;
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
  document.querySelector('#library-operation').textContent=`${op.phase==='verifying'?'Verifying':'Downloading'} · ${op.file || ''} · ${byteSize(op.completed)} / ${byteSize(op.total)}`;
  document.querySelector('#cancel-model-download').disabled=!active;
  for (const id of ['choose-destination','add-model-folder','download-all']) document.querySelector('#'+id).disabled=active || running;
  document.querySelector('#download-all').disabled ||= !data.destination || !libraryData || Object.values(libraryData.sets).every(s=>s.complete);
  if (op.state==='error') libraryStatus.textContent=op.error;
  else if(op.state==='cancelled') libraryStatus.textContent='Canceled. The next download will resume where it stopped.';
  else if(op.state==='done') libraryStatus.textContent=op.message || (op.action==='verify'?'Verification complete.':'Download complete.');
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
async function loadLibrary(revealCards = false) {
  try {
    const data=await request('/api/library');
    libraryData=data;
    modelsReady=!data.selection_error;
    const selection=Object.fromEntries(Object.entries(modelSlots).map(([key,input])=>[key,input.value]));
    modelRootPaths=data.roots;
    fillCatalog(data.catalog);
    fillComponents(selection);
    document.querySelector('#model-destination').textContent=data.destination ? `${data.destination}${data.free==null?'':` · ${byteSize(data.free)} free`}` : 'Choose a folder for model downloads.';
    const folders=document.querySelector('#library-folders');folders.replaceChildren();
    for (const path of data.roots) {
      const row=document.createElement('div');row.className='library-folder';
      const label=document.createElement('span');label.textContent=path;label.title=path;
      row.append(label,libraryButton('×',()=>libraryAction({action:'forget',folder:path}),running || data.operation.state==='running' || data.roots.length===1));
      row.querySelector('button')?.setAttribute('aria-label',`Remove model folder: ${path}`);
      folders.append(row);
    }
    const sets=document.querySelector('#library-sets');
    sets.classList.toggle('reveal-library', revealCards);
    sets.replaceChildren();
    for (const [family,set] of Object.entries(data.sets)) {
      const card=document.createElement('article');card.className='library-card';
      const title=document.createElement('h3');title.textContent=data.catalog.profiles[family].label;
      const summary=document.createElement('p');summary.textContent=set.complete?'Available':`${Object.keys(set.present).length}/${set.roles.length} components · ${byteSize(set.download_bytes)} to download`;
      card.append(title,summary);
      const details=document.createElement('details');
      const detailsTitle=document.createElement('summary');detailsTitle.textContent='Components';details.append(detailsTitle);card.append(details);
      const selections={};
      for(const role of set.roles.filter(role=>role!=='lora')) {
        const label={diffusion:'Generator',encoder:'Encoder',vae:'VAE',vision:'Vision (references)'}[role] || role;
        const row=document.createElement('div');row.className='library-component';
        const caption=document.createElement('label');caption.textContent=label;caption.htmlFor=`library-${family}-${role}`;
        const select=document.createElement('select');select.id=caption.htmlFor;
        select.add(new Option('Not found',''));
        for(const path of set.choices[role]) {const option=new Option(path.split('/').pop(),path);option.title=path;select.add(option);}
        const draft=libraryChoices[family]?.[role];
        select.value=set.choices[role].includes(draft) ? draft : set.present[role] || '';select.disabled=running || data.operation.state==='running';
        const location=document.createElement('small');
        const verification=document.createElement('small');
        function updateLocation() {
          location.textContent=select.value;location.title=select.value;
          const record=data.verification?.[select.value];
          verification.textContent=record ? ({official:'Official file verified by SHA-256',local:'Unchanged since last verification',changed:'Compatible · Contents changed since last verification',unconfirmed:'Compatible · No known upstream hash',failed:'File checksum differs from the verified checksum'}[record.integrity] || '') : '';
        }
        updateLocation();select.addEventListener('change',()=>{libraryChoices[family] ||= {};libraryChoices[family][role]=select.value;updateLocation();});
        selections[role]=select;row.append(caption,select,location,verification);details.append(row);
      }
      if(set.roles.includes('lora')) {
        const row=document.createElement('div');row.className='library-component';
        const label=document.createElement('strong');label.textContent='Turbo LoRA';
        const path=document.createElement('small');
        path.textContent=set.present.lora || 'Missing — downloaded into the Qwen Image 2.1 folder';
        row.append(label,path);details.append(row);
      }
      const actions=document.createElement('div');actions.className='library-toolbar';
      const unavailable=running || data.operation.state==='running';
      actions.append(libraryButton('Select',()=>{
        const selected=Object.fromEntries(Object.entries(selections).map(([role,input])=>[role,input.value]));
        if (Object.values(selected).some(value=>!value)) {libraryStatus.textContent='Locate or download all required components.';return;}
        activeFamily=family;modelProfile.value=family==='z-image-turbo'?'default':family;choosePreset();fillComponents(selected);
        if (Object.entries(selected).some(([role,path])=>path.split('/').pop()!==data.catalog.model_defaults[family][role])) markSamplingCustom();
        libraryStatus.textContent=`${data.catalog.profiles[family].label} selected. Save to apply.`;
      },unavailable || !set.complete));
      actions.append(libraryButton(set.complete?'Verify':'Download / Resume',()=>{
        const components=Object.fromEntries(Object.entries(selections).map(([role,input])=>[role,input.value]));
        if(set.complete && Object.values(components).some(value=>!value)){libraryStatus.textContent='Select all required components for verification.';return;}
        libraryAction({action:set.complete?'verify':'download',families:[family],...(set.complete?{components:{[family]:components}}:{})});
      },unavailable || (!set.complete && !data.destination)));
      if(Object.values(data.managed).some(r=>r.family===family)) actions.append(libraryButton('Remove download',()=>{
        if(window.confirm(`Remove the downloaded files for ${data.catalog.profiles[family].label}? The app will move them to .popai-trash in the model folder. Imported files will be kept.`)) libraryAction({action:'remove',family});
      },unavailable));
      card.append(actions);sets.append(card);
    }
    if(data.error)libraryStatus.textContent=data.error;
    document.querySelector('#download-all').hidden=Object.values(data.sets).every(set=>set.complete);
    document.querySelector('#download-all').textContent=`Download all model sets · ${byteSize(Object.values(data.sets).reduce((sum,set)=>sum+set.download_bytes,0))}`;
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
    document.querySelector('#folder-status').textContent=`${byteSize(data.free)} free`;
    const list=document.querySelector('#folder-list');list.replaceChildren();
    for(const folder of data.folders)list.append(libraryButton(folder.name,()=>browseFolder(folder.path)));
    document.querySelector('#folder-parent').disabled=data.path===data.parent;
    document.querySelector('#folder-select').disabled=false;
  } catch(error) {if(sequence===folderBrowseSequence)document.querySelector('#folder-status').textContent=error.message;}
}
let folderBrowseSequence=0;
async function chooseFolder(mode) {
  folderMode=mode;
  document.querySelector('#folder-title').textContent=mode==='destination'?'Download folder':'Find existing models';
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
  modelStatus.textContent = 'Loading…';
  modelDialog.showModal();
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
      values.forEach(value => sdInputs[key].add(new Option(value === 'auto' ? 'Automatic' : value,value)));
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
    adaptiveWeights.checked = Boolean(catalog.selected.adaptive_weights);
    preloadModel.checked = catalog.selected.preload_model===true;
    acceptProcessingSettings(catalog.selected.prompt_processing);
    fillProcessingSettings(processingSettings);
    modelStatus.textContent = [!processingSupported?processingRestartNotice:'',...catalog.errors].filter(Boolean).join(' · ');
    if (tab === 'models') await loadLibrary(true);
  } catch (error) { modelStatus.textContent = error.message; }
  finally { configuring = false; setBusy(); }
}
modelButton.addEventListener('click', () => openConfig());
hideComposer.addEventListener('click', () => setComposerCollapsed(true));
const adjustConfig = document.querySelector('#adjust-config');
adjustConfig.addEventListener('click', () => openConfig('sd'));

cancelGeneration.addEventListener('click', async () => {
  if (stopping) return;
  stopping = true;
  clearGenerationPreview();
  setBusy();
  status.textContent = 'Canceling…';
  try {
    const canceled = await request('/api/cancel', {method:'POST'});
    running = false;
    clockJob = null;
    status.textContent = canceled.model_loaded?'Generation canceled · Model ready':'Generation canceled · Engine unloaded';
  } catch (error) { status.textContent = error.message; }
  finally { stopping = false; setBusy(); }
});

modelApply.addEventListener('click', async () => {
  if (busy) return;
  if(!processingSupported){modelStatus.textContent=processingRestartNotice;return;}
  configuring = true;
  setBusy(false);
  modelStatus.textContent = 'Saving…';
  try {
    if (modelProfile.value === 'custom') {
      customDraft = readSd();
      customModel = {profile:activeFamily,...Object.fromEntries(['diffusion','encoder','vae','vision'].map(key => [key,modelSlots[key].value]))};
    }
    const settings = {preload_model:preloadModel.checked,prompt_processing:processingDraft(),model_roots:modelRootPaths, profile:activeFamily, sd_custom_model:customModel, sd_profile:modelProfile.value, sd_custom:customDraft, adaptive_weights:adaptiveWeights.checked, resolution:outputResolution.value, aspect_ratio:outputAspect.value, generation_size:generationSize.value, ...Object.fromEntries(Object.entries(modelSlots).map(([key, select]) => [key,select.value]))};
    const saved = await request('/api/models', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(settings)});
    acceptProcessingSettings(saved.prompt_processing);
    if(!processingSupported)throw new Error(processingRestartNotice);
    activeFamily = saved.profile;
    modelsReady = true;
    currentFamily = activeFamily;
    modelButton.title = modelCatalog.profiles[activeFamily].label;
    status.textContent = `${modelButton.title} · ${outputResolution.selectedOptions[0].textContent} · Enter a prompt and press Enter`;
    modelDialog.close();
  } catch (error) { modelStatus.textContent = error.message; }
  finally { configuring = false; setBusy(false); }
});

async function prepareReference(file) {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 20 * 1024 * 1024) {
    throw new Error('Choose a PNG, JPG, or WebP image up to 20 MB.');
  }
  const image = new Image();
  const url = URL.createObjectURL(file);
  try {
    image.src = url;
    try { await image.decode(); }
    catch { throw new Error('Could not open this image. Choose a different file.'); }
    const width = image.naturalWidth;
    const height = image.naturalHeight;
    if (!width || !height || width > 8192 || height > 8192 || width * height > 16777216) {
      throw new Error('Use an image up to 8192 pixels per side and 16 megapixels.');
    }
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    canvas.getContext('2d').drawImage(image, 0, 0);
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    if (!blob || blob.size > 25 * 1024 * 1024) {
      throw new Error('The image is too large. Resize it and try again.');
    }
    return blob;
  } finally {
    URL.revokeObjectURL(url);
  }
}

const poseDialog=document.querySelector('#pose-dialog'),poseFrame=document.querySelector('#pose-frame');

function validPoseState(state){
 if(!state||state.version!==1||!state.P||!Array.isArray(state.layers)||state.layers.length!==17||!state.visible||!state.widths)return false;
 try{return JSON.stringify(state).length<30000&&Object.values(state.P).every(p=>Array.isArray(p)&&p.length===2&&p.every(v=>Number.isFinite(v)&&Math.abs(v)<10000));}catch{return false;}
}
function openPose(){
 if(busy||poseDialog.open||!sketchDialog.open)return;
 poseFrame.src='/pose.html';poseDialog.showModal();
}
poseFrame.addEventListener('load',()=>{
 if(poseDialog.open)poseFrame.contentWindow.postMessage({type:'popai-pose:load',state:null,fromSketch:sketchDialog.open},location.origin);
});
poseDialog.addEventListener('close',()=>{poseFrame.removeAttribute('src');});
window.addEventListener('message',event=>{
 if(event.origin!==location.origin||event.source!==poseFrame.contentWindow||!poseDialog.open)return;
 if(event.data?.type==='popai-pose:close'){poseDialog.close();return;}
 if(event.data?.type!=='popai-pose:submit'||!sketchDialog.open||busy)return;
 const {destination,blob,state}=event.data;
 if(destination!=='sketch'||!(blob instanceof Blob)||blob.type!=='image/png'||!blob.size||blob.size>25*1024*1024||!validPoseState(state))return;
 sketchFrame.contentWindow.postMessage({type:'popai-sketch:insert-pose',blob},location.origin);
 poseDialog.close();
});
let editingSketchId = null;
let initialSketchState = null;
async function openSketch(reference = null) {
  if (busy || !modelsReady || currentFamily === 'z-image-turbo' ||
      (!reference && references.length >= 10) || sketchDialog.open) return;
  let state = validSketchState(reference?.sketch) ? reference.sketch : null;
  if (reference && !state) {
    // Older drawings were stored only as PNG. Reopen one as an editable
    // flattened background; only new objects will have independent selection.
    try {
      const response = await fetch(reference.image);
      if (!response.ok) throw new Error('Missing drawing');
      const png = await response.blob();
      if (png.type !== 'image/png' || !png.size || png.size > 1100000) throw new Error('Drawing too large');
      const base = await new Promise((resolve,reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error('Could not read drawing'));
        reader.readAsDataURL(png);
      });
      state = {version:1,items:[],base};
      if (!validSketchState(state)) throw new Error('Drawing cannot be restored');
    } catch {
      openReferencePreview(reference);
      showPromptNotice('This older sketch is available as an image preview only.');
      return;
    }
  }
  if (reference && !references.some(item => item.id === reference.id)) return;
  editingSketchId = reference?.id || null;
  initialSketchState = state;
  sketchFrame.src = '/sketch.html';
  sketchDialog.showModal();
}
drawReference.addEventListener('click', () => openSketch());
sketchFrame.addEventListener('load', () => {
  if (!sketchDialog.open) return;
  sketchFrame.contentWindow?.postMessage({
    type:'popai-sketch:load', state:initialSketchState
  }, window.location.origin);
});
sketchDialog.addEventListener('close', () => {
  sketchFrame.removeAttribute('src');
  editingSketchId = null;
  initialSketchState = null;
});
window.addEventListener('message', async event => {
  if (event.origin !== window.location.origin || event.source !== sketchFrame.contentWindow || !sketchDialog.open) return;
  if (event.data?.type === 'popai-sketch:pose') {openPose();return;}
  if (event.data?.type === 'popai-sketch:close') {
    sketchDialog.close();
    return;
  }
  if (event.data?.type !== 'popai-sketch:submit') return;
  const blob = event.data.blob;
  const state = event.data.state;
  if (!(blob instanceof Blob) || blob.type !== 'image/png' || !blob.size ||
      blob.size > 25 * 1024 * 1024 || !validSketchState(state)) {
    sketchDialog.close();
    showPromptNotice('The sketch could not be saved as an editable PNG.');
    return;
  }
  const previousId = editingSketchId;
  if (busy || !modelsReady || currentFamily === 'z-image-turbo' ||
      (previousId ? !references.some(reference => reference.id === previousId) : references.length >= 10)) {
    sketchDialog.close();
    showPromptNotice('This model cannot accept another reference image.');
    return;
  }
  sketchDialog.close();
  uploading = true;
  setBusy(false);
  stage.classList.remove('error');
  status.textContent = previousId ? 'Updating drawing…' : 'Attaching drawing…';
  try {
    const result = await request('/api/reference', {method:'POST', headers:{'Content-Type':'image/png'}, body:blob});
    if (previousId) {
      const index = references.findIndex(reference => reference.id === previousId);
      if (index < 0) {
        releaseReferences([result.id]);
        throw new Error('The original drawing is no longer attached.');
      }
      references.splice(index,1,{...result,name:'Sketch 4:3',sketch:state});
      releaseReferences([previousId]);
    } else {
      references.push({...result,name:'Sketch 4:3',sketch:state});
    }
    renderReferences();
    status.textContent = `${references.length} attached · Describe the edit and press Enter`;
  } catch (error) {
    stage.classList.add('error');
    status.textContent = error.message;
  } finally {
    uploading = false;
    setBusy(false);
    prompt.focus();
  }
});

addReference.addEventListener('click', () => {
  if (busy || currentFamily === 'z-image-turbo') return;
  referenceFile.value = '';
  referenceFile.click();
});

referenceFile.addEventListener('change', async () => {
  const files = Array.from(referenceFile.files || []);
  if (!files.length || busy || currentFamily === 'z-image-turbo') return;
  if (references.length + files.length > 10) {
    status.textContent = 'You can attach up to 10 reference images. Remove one to add another.';
    return;
  }
  uploading = true;
  setBusy(false);
  stage.classList.remove('error');
  status.textContent = 'Preparing reference image…';
  try {
    for (const [index, file] of files.entries()) {
      status.textContent = `Preparing reference image ${index + 1} of ${files.length}…`;
      const blob = await prepareReference(file);
      const result = await request('/api/reference', {method: 'POST', headers: {'Content-Type': 'image/png'}, body: blob});
      references.push({...result, name: file.name});
      renderReferences();
    }
    status.textContent = `${references.length} attached · Refer to them as image 1, image 2, etc.`;
  } catch (error) {
    stage.classList.add('error');
    status.textContent = error.message;
  } finally {
    uploading = false;
    setBusy(false);
    prompt.focus();
  }
});

function imageDownloadName(id) {
  const alphabet = 'abcdefghijklmnopqrstuvwxyz';
  let hash = 2166136261;
  for (const character of id) hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);
  let value = hash >>> 0;
  let code = '';
  for (let index = 0; index < 6; index++) {
    code = alphabet[value % alphabet.length] + code;
    value = Math.floor(value / alphabet.length);
  }
  return `popAI-${code}.png`;
}

function clearResult() {
  if (!wallpaper.hidden || rememberedResult) {
    endImageDrag();
    wallpaper.removeAttribute('src');
    save.removeAttribute('href');
    wallpaper.hidden = save.hidden = true;
    imageViewport.classList.remove('has-image');
    shown = null;
    rememberedResult = null;
    saveComposerSession();
  }
}

newGeneration.addEventListener('click', () => {
  if (newGeneration.disabled) return;
  clearThoughtHold();displayThought('idle');
  const nextSeed = randomSeed();
  pageSeed = nextSeed === pageSeed ? (pageSeed + 1) & 0x7fffffff : nextSeed;
  hiddenImageId = latestImageId || shown || hiddenImageId;
  const identity = currentJobId || latestImageId || shown;
  if (identity && /^[0-9a-f]{32}$/.test(identity)) {
    discardJobId = identity;
    discardJob(identity);
  }
  clearGenerationPreview();
  clearResult();
  resultError = null;
  stage.classList.remove('error');
  welcome.hidden = false;
  updateMascot();
  saveComposerSession();
  showPromptNotice('Ready for a new generation. Press Enter to generate.');
  prompt.focus();
});

async function showResult(job, announce = true) {
  const epoch = previewEpoch;
  const width = job.width || 1920;
  const height = job.height || 1080;
  const image = new Image();
  image.src = job.image;
  await image.decode();
  if (epoch !== previewEpoch) return false;
  if (image.naturalWidth !== width || image.naturalHeight !== height) {
    throw new Error('The final PNG has unexpected dimensions.');
  }
  image.id = 'wallpaper';
  image.alt = 'Generated wallpaper';
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
  updateMascot();
  save.href = job.image;
  save.download = imageDownloadName(job.id);
  save.setAttribute('aria-label',`Download image, ${width} by ${height} pixels`);
  save.hidden = false;
  shown = job.id;
  rememberedResult = {id: job.id, width, height};
  saveComposerSession();
  if (announce) playCompletionSound(job.id);
  return true;
}

function discardJob(identity) {
  return request('/api/jobs/'+identity+'/discard', {method:'POST'})
    .then(()=>{if(discardJobId===identity)discardJobId=null;})
    .catch(()=>{}); // Retry a disconnected request on the next successful poll.
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
    acceptProcessingSettings(enhancerState.options);
    modelsReady=job.models_ready!==false;
    const jobKey=JSON.stringify([job.id || null,job.state]);
    if(jobKey!==observedJobKey || job.state==='running')promptNotice=null;
    observedJobKey=jobKey;
    reconcileReferences(job.missing_references);
    const initialStatus = !initialStatusReceived;
    initialStatusReceived = true;
    currentJobId = job.id || null;
    if (discardJobId) {
      if (currentJobId === discardJobId && job.state !== 'running') discardJob(discardJobId);
      else if (currentJobId !== discardJobId) discardJobId=null;
    }
    latestImageId = job.state === 'done' && job.image ? job.id : null;
    stage.classList.remove('error');
    syncClock(job);
    currentFamily = job.profile || currentFamily;
    setBusy(job.state === 'running');
    adjustConfig.hidden = !(job.config_error || job.state === 'error' && job.error_info?.action === 'settings');
    recoverableJob = job.retryable ? job.id : null;
    retryFinalize.hidden = !recoverableJob;
    if (initialStatus && !latestImageId && !job.preview && rememberedResult) {
      try {
        const result = rememberedResult;
        if (!await showResult({...result, image: `/images/${result.id}.png`}, false)) return;
      } catch {
        rememberedResult = null;
        saveComposerSession();
      }
    }
    if (job.config_error && job.state === 'idle') status.textContent = job.config_error;
    if (job.state === 'running') {
      showGenerationPreview(job);
    } else if (job.state === 'done' && (!job.image || job.id === hiddenImageId)) {
      clearGenerationPreview();
      status.textContent = 'Enter a prompt and press Enter';
    } else if (job.state === 'done') {
      if (shown !== job.id) {
        try {
          if (!await showResult(job, !initialStatus)) return;
          resultError = null;
        } catch (error) {
          clearGenerationPreview();
          shown = job.id;
          resultError = 'Could not open the final PNG. Reload the page to try again.';
          shown = null;
          save.hidden = true;
        }
      }
      if (resultError) {
        stage.classList.add('error');
        status.textContent = resultError;
      } else {
        status.textContent = `Ready · Total ${formatDuration(job.elapsed)}`;
      }
    } else if (job.state === 'error') {
      clearGenerationPreview();
      stage.classList.add('error');
      status.textContent = job.error;
      modelButton.title = 'Adjust settings';
    } else if (job.state === 'cancelled') {
      clearGenerationPreview();
      status.textContent = job.model_loaded?'Generation canceled · Model ready':'Generation canceled · Enter another prompt to create more';
    } else {
      clearGenerationPreview();
    }
    if(job.state!=='running') {
      if(job.config_error)status.textContent=job.config_error;
      else if(job.preload_error && !job.model_loaded && job.state==='idle')status.textContent='Preload failed · '+job.preload_error;
      else if(promptNotice?.jobKey===observedJobKey && !resultError)status.textContent=promptNotice.text;
    }
  } catch (error) {
    clearGenerationPreview();
    stage.classList.add('error');
    clockJob = null;
    timeEstimate.hidden = true;
    status.textContent = 'Server disconnected. Reconnecting…';
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
const composer = document.querySelector('.composer');
const composerFields = document.querySelector('#composer-fields');
const composerMessage = document.querySelector('.composer-message');
function setComposerCollapsed(collapsed) {
  composer.classList.toggle('is-collapsed', collapsed);
  composerFields.inert = collapsed;
}

composerMessage.addEventListener('pointerenter', event => {
  if (event.pointerType !== 'touch' && composerFields.inert) setComposerCollapsed(false);
});
composerMessage.addEventListener('pointerdown', () => {
  if (composerFields.inert) setComposerCollapsed(false);
});

window.addEventListener('pagehide',()=>{if(!enhancing)savePromptDraft();});
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
restoreComposerSession();
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
  clearThoughtHold();displayThought('idle');
  status.textContent = 'Starting…';
  try {
    const effectivePrompt=generationPrompt(prompt.value.trim(),references);
    if(effectivePrompt.length>16000)throw new Error('Shorten the description to leave room for sketch reference instructions.');
    await request('/api/generate', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({prompt: effectivePrompt, seed: pageSeed, reference: references.map(reference => reference.id)})});
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
