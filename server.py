#!/usr/bin/env python3
"""Local portable image generation service."""
import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import signal
import struct
import tempfile
import shutil
import subprocess
import threading
import time
import uuid
import zlib
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import hardware
import model_catalog
from model_library import ModelLibrary
from prompt_enhancer import PromptEnhancer, MAX_PROMPT_CHARS, normalize_prompt_processing
from errors import native_failure, explain
from jobs import JobStore
from image_pipeline import crop_box, validate_image, finalize, prepare_qwen_reference
from processes import spawn
from resident import ResidentEngine, terminate
from app_config import APP_ROOT, RESOURCE_ROOT, SettingsStore, normalize_roots, local_path, HARDWARE_DEFAULTS

ROOT = APP_ROOT
WEB = RESOURCE_ROOT / 'web'
IMAGE_NAME = re.compile(r'[0-9a-f]{32}\.png')
REFERENCE_ID = re.compile(r'[0-9a-f]{32}')
MAX_REFERENCE_BYTES = 25 * 1024 * 1024
DEFAULT_MODEL_DIR = ROOT / 'models'
NCNN_EXECUTABLE = ROOT / 'backends/upscayl-ncnn/upscayl-bin'
DEFAULT_UPSCALER = ROOT / 'backends/upscayl-ncnn/models/realesrgan-x4plus.bin'
from catalog import ASPECT_RATIOS, GENERATION_SIZES, image_geometry, PROFILES, RESOLUTIONS, SD_DEFAULT, SD_DEFAULTS, CUSTOM_DEFAULTS, MODEL_DEFAULTS, SAMPLERS, SCHEDULERS, normalize_sd, generation_profile
from catalog import GENERATION_SIZE_LABELS, SD_PROFILE_FAMILIES, PROFILE_FILES, component_family
MODEL_FILES = {
    'diffusion': 'z_image_turbo-Q8_0.gguf',
    'encoder': 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf',
    'vae': 'ae.safetensors',
}


@lru_cache(maxsize=4)
def _runner_options(executable, revision):
    # The packaged CLI prints help before creating a Vulkan device. Check once
    # per binary revision so older builds or incompatible loaders can fall back.
    try:
        help_text = subprocess.run([str(executable), '-h'], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    return frozenset(flag for flag in ('-2', '-P') if f'  {flag} '.encode() in help_text)


def _companion_upscaler(executable):
    candidate = executable.with_name('upscayl-chain')
    try:
        stat = candidate.stat()
    except OSError:
        return candidate, frozenset()
    return candidate, _runner_options(candidate, (stat.st_ino, stat.st_ctime_ns))


def _encoded_size(job):
    if job.get('native_final_png'):
        return job.get('width'), job.get('height')
    return job.get('upscaled_width'), job.get('upscaled_height')


class GenerationManager:
    def __init__(self, executable, model_dir, outputs, logs, upscale_model=DEFAULT_UPSCALER, model_roots=None, store=None, *, keep_loaded=True):
        self.executable = Path(executable).resolve()
        self.model_dir = Path(model_dir).resolve()
        self.model_roots = normalize_roots(model_roots or [str(self.model_dir)])
        self.store = store or SettingsStore(ROOT)
        self.library = ModelLibrary(self.store.root, self.model_roots)
        self.config_error = None
        self.resident_policy = None
        self.model = self.model_dir / MODEL_FILES['diffusion']
        self.encoder = self.model_dir / MODEL_FILES['encoder']
        self.vae = self.model_dir / MODEL_FILES['vae']
        self.upscale_model = Path(upscale_model).resolve()
        self.upscale_executable = NCNN_EXECUTABLE
        self.outputs = Path(outputs).resolve()
        self.logs = Path(logs).resolve()
        self.temporary = tempfile.TemporaryDirectory(prefix='popai-')
        self.workspace = Path(self.temporary.name)
        self.references = self.workspace / 'references'
        self.outputs.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)
        self.enhancer = PromptEnhancer(self.logs)
        self.references.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.operation_lock = threading.RLock()
        self.cancel_event = threading.Event()
        self.resident = ResidentEngine()
        self.keep_loaded = keep_loaded
        self.preload_model = False
        self.preload_error = None
        self.adaptive_weights = False
        self.resolution = '1080p'
        self.aspect_ratio = '16:9'
        self.generation_size = 'standard'
        self.jobs = JobStore(self.outputs.parent)
        self.job = {'state': 'idle', 'image': None, 'error': None}
        self.process = None
        self.worker = None
        self.closed = False
        self.profile = 'z-image-turbo'
        self.sd_profile = 'default'
        self.sd_custom = dict(SD_DEFAULT)
        self.sd_custom_model = {}
        self.vision = None
        self.last_preview_id=None
        self.previous_preview_id=None
        self.previous_preview_until=0
        self.reference_seen={}
        self.reference_released=set()
        self.next_cleanup=0
        self._restore_job()

    def _restore_job(self):
        saved = self.jobs.latest()
        if not saved:
            return
        self.job = saved
        if saved['state'] == 'running':
            saved.update(state='error', phase='interrupted', error='The app closed before the job finished.', finished=time.time())
        saved['retryable'] = self._recoverable(saved)
        self.jobs.save(saved)

    def _artifact_paths(self, job):
        if job.get('artifacts_version')==2:
            directory=self.workspace/'jobs'/job['id']
            return directory/'base.png',directory/'upscaled.png'
        if job.get('artifacts_version')==1:
            directory=self.jobs.directory/'artifacts'/job['id']
            return directory/'base.png',directory/'upscaled.png'
        return self.outputs/(job['id']+'-base.png'),self.outputs/(job['id']+'-upscaled.png')

    def image_path(self, identity):
        temporary = self.workspace/'jobs'/identity/'final.png'
        return temporary if temporary.is_file() else self.outputs/(identity+'.png')

    def asset_bytes(self, identity, reference=False):
        # Keep the snapshot alive through the download even if pruning follows.
        with self.lock:
            path=self.references/(identity+'.png') if reference else self.image_path(identity)
            try:return path.read_bytes() if path.is_file() and not path.is_symlink() else None
            except FileNotFoundError:return None

    def base_preview_bytes(self, identity):
        with self.lock:
            if self.job.get('id') != identity or self.job.get('state') != 'running':
                return None
            base, _ = self._artifact_paths(self.job)
            phase = self.job.get('phase')
            if phase == 'generating':
                path = base.with_name('step-preview.png')
            elif phase in ('upscaling', 'finalizing'):
                path = base
            else:
                return None
            try:
                if path.is_symlink():
                    return None
                data = path.read_bytes()
            except OSError:
                return None
            # The CLI overwrites its preview in place. Ignore incomplete writes.
            if not data.endswith(b'\0\0\0\0IEND\xaeB\x60\x82'):
                return None
            if self.last_preview_id and self.last_preview_id != identity:
                old_result = self.workspace/'jobs'/self.last_preview_id/'final.png'
                try:
                    old_result.unlink(missing_ok=True)
                except OSError:
                    pass  # Temporary storage will be cleaned up at session close.
                self.last_preview_id = None
            return data

    def touch_references(self, identities):
        if not isinstance(identities,list) or len(identities)>10 or any(not isinstance(i,str) or not REFERENCE_ID.fullmatch(i) for i in identities):
            raise ValueError('Invalid reference image list.')
        with self.lock:
            missing=[]
            for identity in identities:
                if identity not in self.reference_released and (self.references/(identity+'.png')).is_file():
                    self.reference_seen[identity]=time.time()
                else:missing.append(identity)
            return missing

    def release_references(self, identities):
        if not isinstance(identities,list) or len(identities)>128 or any(not isinstance(i,str) or not REFERENCE_ID.fullmatch(i) for i in identities):
            raise ValueError('Invalid reference image list.')
        with self.operation_lock,self.lock:
            self.reference_released.update(identities)
            self._prune_temporary_locked()
        return {'released':identities}

    def _prune_temporary_locked(self):
        if self.closed:return
        now=time.time()
        keep={self.job.get('id'),self.last_preview_id}
        if now<self.previous_preview_until:keep.add(self.previous_preview_id)
        directory=self.workspace/'jobs'
        if directory.is_dir():
            for path in directory.iterdir():
                if REFERENCE_ID.fullmatch(path.name) and path.name not in keep and path.is_dir() and not path.is_symlink():
                    try:shutil.rmtree(path)
                    except OSError:pass
        active=set(self.job.get('reference_ids',[])) if self.job.get('state')=='running' else set()
        for path in self.references.glob('*.png'):
            identity=path.stem
            if not REFERENCE_ID.fullmatch(identity) or identity in active:continue
            try:
                seen=self.reference_seen.get(identity,path.stat().st_mtime)
                if identity in self.reference_released or now-seen>3600:
                    path.unlink(missing_ok=True)
                    self.reference_seen.pop(identity,None)
            except OSError:continue
        self.reference_released={i for i in self.reference_released if (self.references/(i+'.png')).exists()}
        self.next_cleanup=time.monotonic()+30

    def cleanup_temporary(self):
        with self.lock:
            if time.monotonic()>=self.next_cleanup:self._prune_temporary_locked()

    def _recoverable(self, job):
        if not job.get('id') or job.get('state') == 'done':
            return False
        base,upscaled=self._artifact_paths(job)
        for path, size in ((upscaled, _encoded_size(job)), (base, (job.get('base_width'), job.get('base_height')))):
            try:
                self._validate_image(path, size)
                return True
            except (OSError,RuntimeError,KeyError):
                pass
        return False

    def _publish(self, **values):
        with self.lock:
            self.job.update(values)
            self.jobs.save(self.job)

    def retry_finalize(self, identity):
        with self.operation_lock:
            if self.enhancer.status()['busy']:
                raise RuntimeError('Wait for prompt enhancement to finish.')
            with self.lock:
                if self.closed or self.job['state'] == 'running':
                    raise RuntimeError('Wait for the current job to finish.')
                if self.job.get('id') != identity or not self._recoverable(self.job):
                    raise ValueError('This job has no valid base image to finish.')
                if self.job.get('artifacts_version')!=2:
                    old_paths=self._artifact_paths(self.job)
                    directory=self.workspace/'jobs'/identity
                    directory.mkdir(parents=True,exist_ok=True)
                    for source,name in zip(old_paths,('base.png','upscaled.png')):
                        if source.is_file() and not source.is_symlink():
                            shutil.copy2(source,directory/name)
                    self.job['artifacts_version']=2
                previous_job=dict(self.job)
                self.cancel_event.clear()
                self.job.update(state='running', phase='upscaling', error=None, retryable=False, started=time.time(), finalize_only=True, estimated_seconds=None)
                self.job.pop('finished',None)
                try:
                    self.jobs.save(self.job)
                except OSError as exc:
                    self.job=previous_job
                    raise explain(exc) from exc
                self.worker = threading.Thread(target=self._generate, args=('',dict(self.job),[],True), daemon=True)
                self.worker.start()
                return dict(self.job)

    def model_settings(self):
        with self.lock:
            return {'profile': self.profile, 'diffusion': str(self.model),
                    'encoder': str(self.encoder) if self.encoder else '', 'vae': str(self.vae) if self.vae else '',
                    'vision': str(self.vision) if self.vision else '', 'keep_loaded': self.keep_loaded, 'preload_model': self.preload_model,
                    'adaptive_weights': self.adaptive_weights, 'prompt_processing':dict(self.enhancer.options),
                    'resolution': self.resolution, 'aspect_ratio':self.aspect_ratio, 'generation_size':self.generation_size, 'model_roots': [str(p) for p in self.library.roots()],
                    'hardware': dict(HARDWARE_DEFAULTS), 'schema_version': 2, 'sd_profile':self.sd_profile,
                    'sd_default':dict(SD_DEFAULT), 'sd_defaults':SD_DEFAULTS, 'sd_custom':dict(self.sd_custom), 'sd_custom_model':dict(self.sd_custom_model)}

    def model_catalog(self, roots=None):
        roots = normalize_roots(roots) if roots is not None else self.library.roots()
        files, errors = set(), []
        for root in roots:
            if not root.is_dir():
                errors.append(f'Folder unavailable: {root}')
                continue
            try:
                for path in root.rglob('*'):
                    if '.popai-trash' in path.parts:
                        continue
                    if path.suffix.lower() in {'.gguf','.safetensors'} and path.is_file() and path.resolve().is_relative_to(root):
                        files.add(str(path.resolve()))
            except OSError as exc:
                errors.append(f'Could not read {root}: {exc}')
        components=self._catalog_components(files)
        families={role:{component_family(f,role) for f in PROFILES}
                  for role in ('diffusion','encoder','vae','vision')}
        files={p for p,c in components.items() if c['role'] in families and c['family'] in families[c['role']]}
        return {'files': sorted(files), 'root': str(roots[0]), 'roots': [str(p) for p in roots],
                'errors': errors, 'selected': self.model_settings(),
                'profiles': PROFILES, 'sd_profile_families': SD_PROFILE_FAMILIES, 'model_defaults':MODEL_DEFAULTS, 'profile_files':PROFILE_FILES, 'custom_defaults':CUSTOM_DEFAULTS, 'samplers':SAMPLERS, 'schedulers':SCHEDULERS, 'resolutions': RESOLUTIONS, 'aspect_ratios':list(ASPECT_RATIOS), 'generation_sizes':GENERATION_SIZE_LABELS, 'resolution_options':{ratio:{key:[image_geometry(key,ratio)['width'],image_geometry(key,ratio)['height']] for key in RESOLUTIONS} for ratio in ASPECT_RATIOS}, 'components': {p:components[p] for p in files}}

    def library_status(self):
        catalog=self.model_catalog()
        data=self.library.snapshot()
        sets={}
        for family,defaults in MODEL_DEFAULTS.items():
            present={}
            choices={}
            required=[entry['role'] for entry in self.library.manifest[family]]
            for role in required:
                if role=='lora':
                    # Imported generators can use a LoRA kept in the organized
                    # download folder; sd-cli accepts its separate directory.
                    lora=self.library.find_lora(family, present.get('diffusion'))
                    paths=[str(lora)] if lora else []
                else:
                    expected=component_family(family,role)
                    paths=[p for p in catalog['files'] if catalog['components'][p]['role']==role and catalog['components'][p]['family']==expected]
                    preferred=catalog['selected'].get(role) if catalog['selected']['profile']==family else None
                    paths.sort(key=lambda p:(p!=preferred,Path(p).name!=defaults[role],p.casefold()))
                choices[role]=paths
                if paths:present[role]=paths[0]
            remaining=0
            for component in self.library.manifest[family]:
                if component['role'] in present:continue
                target=self.library.download_target(family, component)
                partial=target.with_name(target.name+'.part') if target else None
                received=min(component['size'],partial.stat().st_size) if partial and partial.is_file() else 0
                remaining+=component['size']-received
            sets[family]={'present':present,'choices':choices,'roles':required,
                          'complete':all(role in present for role in required),'download_bytes':remaining}
        destination=data['destination']
        data.update(sets=sets,catalog=catalog,selection_error=self.selection_error(),verification=self.library.verifications(),needs_setup=not any(s['complete'] for s in sets.values()),
                    free=shutil.disk_usage(destination).free if destination and Path(destination).is_dir() else None)
        return data

    def library_action(self,body):
        action=body.get('action')
        if action=='cancel':return self.library.cancel()
        with self.operation_lock:
            if self.closed or self.job['state']=='running':
                raise RuntimeError('Wait for image generation to finish before managing models.')
            if action in ('add','destination','forget'):
                result=self.library.configure(body.get('folder'),action)
                self._sync_selection()
                return result
            if action=='remove':
                result=self.library.remove(body.get('family'))
                self._sync_selection()
                return result
            if action in ('download','verify'):
                sets=self.library_status()['sets']
                present={f:s['present'] for f,s in sets.items()}
                requested=body.get('components')
                if action=='verify' and requested is not None:
                    families=body.get('families')
                    if not isinstance(families,list) or not families or any(not isinstance(f,str) or f not in sets for f in families):
                        raise ValueError('Select a valid model set to verify.')
                    if not isinstance(requested,dict) or set(requested)!=set(families):
                        raise ValueError('Select the components in the set you want to verify.')
                    for family,selection in requested.items():
                        selectable=set(sets[family]['roles'])-{'lora'}
                        if not isinstance(selection,dict) or set(selection)!=selectable:
                            raise ValueError('Select all required components before verifying.')
                        if any(not isinstance(path,str) or path not in sets[family]['choices'][role] for role,path in selection.items()):
                            raise ValueError('Select compatible files from the library folders.')
                        if 'lora' in sets[family]['roles']:
                            lora=self.library.find_lora(family, selection['diffusion'])
                            if not lora:
                                raise ValueError('Locate or download the Turbo LoRA for this model.')
                            selection['lora']=str(lora)
                        present[family]=dict(selection)
                return self.library.start(action,body.get('families'),present)
            raise ValueError('Invalid model action.')

    def selection_error(self):
        roots=self.library.roots()
        verified=self.library.verifications()
        for label,path in (('Generator',self.model),('Encoder',self.encoder),('VAE',self.vae)):
            if not path or not path.is_file() or not any(path.resolve().is_relative_to(root) for root in roots):
                return f'{label} is unavailable in the selected set. Choose components on the Models tab.'
            if verified.get(str(path),{}).get('integrity')=='failed':
                return f'{label} in the selected set differs from the verified file. Check the component on the Models tab.'
        if PROFILES.get(self.profile,{}).get('lora') and not self.library.find_lora(self.profile,self.model):
            return 'Qwen Turbo LoRA is missing. Download it from the Models tab.'
        return None

    def _sync_selection(self):
        self.model_roots=self.library.roots()
        if self.selection_error():self.resident.stop()

    @staticmethod
    def _catalog_components(files):
        result = {}
        for path in files:
            try:
                data = model_catalog.inspect(path)
                role, family = model_catalog.identify(data)
                result[path] = {'role':role,'family':family,'name':data['metadata'].get('general.name',''), 'architecture':data['metadata'].get('general.architecture') or data['metadata'].get('architecture') or family, 'profile':model_catalog.diffusion_profile(path,data) if role in ('diffusion','unknown') else None}
            except (ValueError,OSError):
                result[path] = {'role':'unknown','family':'unknown','name':''}
        return result

    def configure(self, settings, persist=False, allow_missing=False):
        with self.operation_lock:
            return self._configure(settings, persist, allow_missing)

    def _configure(self, settings, persist=False, allow_missing=False):
        if not isinstance(settings, dict) or settings.get('profile') not in PROFILES:
            raise ValueError('Select a valid set of components.')
        if self.enhancer.status()['busy']:
            raise RuntimeError('Wait for prompt processing to finish before changing settings.')
        prompt_processing = normalize_prompt_processing(settings.get('prompt_processing', self.enhancer.options))
        sd_profile = settings.get('sd_profile', self.sd_profile)
        if sd_profile == 'default' and settings['profile'] == 'z-image-turbo' and settings.get('experimental_five_steps') is True:
            sd_profile = 'z-image-5'
        # Keep a previously saved preview ID compatible with the official 4-step preset.
        if sd_profile == 'qwen-image21-4-experimental':
            sd_profile = 'qwen-image21-4'
        if sd_profile not in (*SD_DEFAULTS,'custom'):
            raise ValueError('Select an available profile or Custom.')
        if sd_profile != 'custom' and settings['profile'] != SD_PROFILE_FAMILIES[sd_profile]:
            raise ValueError('The selected set does not match the default profile.')
        sd_custom = normalize_sd(settings.get('sd_custom', self.sd_custom))
        custom_model = settings.get('sd_custom_model',self.sd_custom_model)
        if not isinstance(custom_model,dict):
            raise ValueError('Invalid custom components.')
        custom_model = {k:v for k,v in custom_model.items() if k in ('profile','diffusion','encoder','vae','vision') and isinstance(v,str)}
        if custom_model and custom_model.get('profile') not in PROFILES:
            custom_model = {}
        preload_model = settings.get('preload_model', self.preload_model)
        if type(preload_model) is not bool:
            raise ValueError('Choose whether to preload the selected model on startup.')
        adaptive_weights = settings.get('adaptive_weights', self.adaptive_weights)
        if not isinstance(adaptive_weights, bool):
            raise ValueError('Choose whether to enable automatic weight distribution.')
        resolution = settings.get('resolution', self.resolution)
        if not isinstance(resolution, str) or resolution not in RESOLUTIONS:
            raise ValueError('Select a resolution between 720p and 4K UHD.')
        aspect_ratio = settings.get('aspect_ratio',self.aspect_ratio)
        generation_size = settings.get('generation_size',self.generation_size)
        if not isinstance(aspect_ratio,str) or aspect_ratio not in ASPECT_RATIOS:
            raise ValueError('Select a valid aspect ratio.')
        if not isinstance(generation_size,str) or generation_size not in GENERATION_SIZES:
            raise ValueError('Select an available generation size.')
        paths = {}
        roots = normalize_roots(settings.get('model_roots', [str(p) for p in self.library.roots()]))
        for key in ('diffusion', 'encoder', 'vae', 'vision'):
            value = settings.get(key, '')
            if key == 'vision' and not PROFILES[settings['profile']].get('components',{}).get('vision'):
                paths[key] = None
                continue
            if key == 'vision' and not value:
                paths[key] = None
                continue
            if not isinstance(value, str) or not value or '\0' in value:
                raise ValueError(f'The {key} component is missing for {PROFILES[settings["profile"]]["label"]}. Check the model folders.')
            path = local_path(value)
            if path.suffix.lower() not in {'.gguf', '.safetensors'} or (not allow_missing and (not any(path.is_relative_to(root) for root in roots) or not path.is_file())):
                raise ValueError(f'Missing or invalid component: {key}. Choose a file from a model folder.')
            paths[key] = path
        if not allow_missing:
            model_catalog.validate(settings['profile'], paths)
            verified=self.library.verifications()
            if any(verified.get(str(path),{}).get('integrity')=='failed' for path in paths.values() if path):
                raise ValueError('A component differs from the verified file. Check the Models tab.')
        if sd_profile == 'custom':
            custom_model = {'profile':settings['profile'], **{key:str(value) if value else '' for key,value in paths.items()}}
        with self.lock:
            if self.closed or self.job['state'] == 'running':
                raise RuntimeError('Wait for the job to finish before switching models.')
            if persist:
                saved = {'profile': settings['profile'], 'adaptive_weights': adaptive_weights, 'preload_model': preload_model,
                         'resolution': resolution, 'aspect_ratio':aspect_ratio, 'generation_size':generation_size, 'prompt_processing':prompt_processing,
                         'model_roots': [str(p) for p in roots], 'sd_profile':sd_profile, 'sd_custom':sd_custom, 'sd_custom_model':custom_model,
                         **{key: str(value) if value else '' for key, value in paths.items()}}
                self.store.save(saved)
            old_sd = self.sd_custom if self.sd_profile=='custom' else SD_DEFAULTS[self.sd_profile]
            new_sd = sd_custom if sd_profile=='custom' else SD_DEFAULTS[sd_profile]
            reload_required = old_sd['mmap'] != new_sd['mmap'] or self.profile != settings['profile'] or (self.model,self.encoder,self.vae) != tuple(paths[key] for key in ('diffusion','encoder','vae'))
            if reload_required or adaptive_weights != self.adaptive_weights:
                self.resident.stop()
            self.sd_profile, self.sd_custom = sd_profile, sd_custom
            self.sd_custom_model = custom_model
            self.adaptive_weights = adaptive_weights
            self.preload_model = preload_model
            self.preload_error = None
            self.enhancer.options = prompt_processing
            self.resolution = resolution
            self.aspect_ratio, self.generation_size = aspect_ratio, generation_size
            self.model_roots = roots
            self.config_error = None
            self.profile = settings['profile']
            self.model, self.encoder, self.vae, self.vision = (paths[key] for key in ('diffusion', 'encoder', 'vae', 'vision'))
        return self.model_settings()

    def _resident_command(self, settings, policy, mmap, lora=None):
        executable = self.executable.with_name('sd-server')
        if not executable.is_file():
            raise RuntimeError('The persistent engine has not been built. Run ./build.sh.')
        device = policy['generator']['ggml']
        weights = ['--auto-fit', 'on'] if settings.get('adaptive_weights') else ['--offload-to-cpu']
        command = [str(executable), '--diffusion-model', settings['diffusion'],
                   '--llm', settings['encoder'], '--vae', settings['vae'],
                   '--backend', f'diffusion={device},te={device},vae={device}',
                   *weights, *(['--mmap'] if mmap else [])]
        if settings.get('preload_model'):
            command.append('--eager-load')
        if lora:
            command.extend(['--lora-model-dir', str(lora.parent)])
        return command

    @staticmethod
    def _resident_environment(env, settings, mmap):
        result = dict(env)
        if settings.get('preload_model') and mmap:
            # MAP_POPULATE faults in file-backed pages in the native process.
            result['SD_MMAP_FLAGS'] = 'populate'
        return result

    def preload_selected_model(self):
        """Load the selected resident model once at startup, without submitting a job."""
        if not self.preload_model or not self.keep_loaded:
            return False
        try:
            if self.config_error or self.selection_error():
                raise RuntimeError(self.config_error or self.selection_error())
            settings = self.model_settings()
            model_catalog.validate(self.profile, {'diffusion':self.model,'encoder':self.encoder,'vae':self.vae,'vision':None})
            policy, env = hardware.select(hardware.discover(self.executable), HARDWARE_DEFAULTS)
            sd = self.sd_custom if self.sd_profile == 'custom' else SD_DEFAULTS[self.sd_profile]
            lora = self.library.find_lora(self.profile,self.model) if PROFILES[self.profile].get('lora') else None
            command = self._resident_command(settings, policy, sd['mmap'], lora)
            deadline = time.monotonic() + 300
            self.resident.ensure(command, self._resident_environment(env, settings, sd['mmap']), ROOT, self.logs / 'resident.log',
                                 None, lambda: self._check_active(deadline))
            self.resident_policy = policy
            return True
        except (OSError, RuntimeError, ValueError, MemoryError) as exc:
            self.resident.stop()
            self.resident_policy = None
            self.preload_error = str(explain(exc))
            return False

    def _native_progress(self, progress):
        with self.lock:
            previous = self.job.get('progress',{})
            current = dict(progress)
            if current.get('stage') == 'sampling' and current.get('unit') == 'steps':
                completed, total = current.get('completed'), current.get('total')
                if isinstance(completed,int) and isinstance(total,int) and 0 < completed <= total:
                    if (previous.get('stage'),previous.get('completed'),previous.get('pass')) == ('sampling',completed,current.get('pass')):
                        current.update(remaining_seconds=previous.get('remaining_seconds'),updated=previous.get('updated'))
                    else:
                        elapsed = max(0,current.get('stage_elapsed_ms',0))/1000
                        current.update(remaining_seconds=elapsed/completed*(total-completed),updated=time.time())
            self.job['progress'] = current

    def _cli_progress(self, state):
        try:
            log = self.logs/(state['id']+'.log')
            with log.open('rb') as stream:
                offset = max(0, os.fstat(stream.fileno()).st_size - 32768)
                stream.seek(offset)
                text = stream.read().decode('utf-8',errors='replace')
            _, start, sampling = text.rpartition('[I] generating image:')
            if not start:
                # Progress bars from Qwen3-VL conditioning, model loading and VAE
                # are not diffusion steps. Never report them as 1/10 or 1/128 steps.
                if '[I] generate_image ' in text:
                    return {'stage':'conditioning'}
                if '[I] loading ' in text:
                    return {'stage':'loading_model'}
                return None
            if '[I] sampling completed, taking ' in sampling:
                return {'stage':'vae_decode'}
            matches = re.findall(r'(\d+)/(\d+)\s*-\s*([\d.]+)(s/it|it/s)',sampling)
            if not matches:
                return {'stage':'conditioning'}
            # Each emitted record measures a denoising step. Distinguish its
            # exact count from similarly formatted conditioning and decode bars.
            expected = state.get('settings',{}).get('sd',{}).get('steps')
            completed,total = map(int,matches[-1][:2])
            if expected is not None and total != int(expected):
                return None
            steps = {}
            for done,count,speed,unit in matches:
                if int(count)==total and float(speed)>0:
                    steps[int(done)] = float(speed) if unit=='s/it' else 1/float(speed)
            if not 0 < completed <= total or not steps:
                return None
            # The first iteration includes graph compilation; do not multiply
            # that one-time startup cost across all remaining iterations.
            warmed = [duration for step,duration in sorted(steps.items()) if step > 1]
            recent = (warmed[-3:] if warmed else [steps[completed]])
            seconds = sum(recent)/len(recent)*(total-completed)
            return {'stage':'sampling','unit':'steps','completed':completed,'total':total,
                    'remaining_seconds':seconds,'updated':log.stat().st_mtime}
        except (OSError,ValueError,KeyError):
            return None

    def _upscale_progress(self, state):
        try:
            separate_first = state.get('upscale_passes') == 2 and state.get('upscale_pass') == 1 and not state.get('upscale_chained')
            suffix = '-upscale-first.log' if separate_first else '-upscale.log'
            log = self.logs/(state['id']+suffix)
            with log.open('rb') as stream:
                stream.seek(-min(log.stat().st_size,16384),os.SEEK_END)
                text = stream.read().decode('utf-8',errors='replace')
            updated = log.stat().st_mtime
            started = state.get('phase_started',updated)
            if updated < started:
                return None
            if state.get('upscale_chained'):
                second = re.search(r'^\[popAI\] upscale pass 2 (\d+)\r?$', text, re.M)
                if second:
                    started = int(second[1]) / 1000
                    state.update(upscale_pass=2, phase_started=started)
                    text = text[second.end():]
            matches = re.findall(r'(?:^|[\r\n])\s*(\d+(?:\.\d+)?)%\s*(?=[\r\n]|$)',text)
            if not matches:
                return None
            percent = min(100,max(0,float(matches[-1])))
            remaining = max(0,updated-started)/percent*(100-percent) if percent>0 else None
            return {'stage':'upscaling','unit':'percent','completed':percent,'total':100,
                    'remaining_seconds':remaining,'updated':updated}
        except (OSError,ValueError,KeyError):
            return None

    def status(self):
        self.cleanup_temporary()
        with self.lock:
            state = dict(self.job)
            if state.get('state') == 'done' and state.get('image') and not self.image_path(state['id']).is_file():
                state['image'] = None
        if state.get('started'):
            state['elapsed'] = round(state.get('finished', time.time()) - state['started'], 1)
        if (state.get('state')=='running' and state.get('phase')=='generating'
                and not state.get('settings',{}).get('keep_loaded')):
            # The CLI progress parser is only used when persistence is disabled.
            state['progress'] = self._cli_progress(state)
        if state.get('state')=='running' and state.get('phase')=='upscaling':
            state['progress'] = self._upscale_progress(state)
        progress = dict(state.get('progress') or {})
        if progress.get('remaining_seconds') is not None and progress.get('updated'):
            progress['remaining_seconds'] = max(0,progress['remaining_seconds']-(time.time()-progress['updated']))
        state['progress'] = progress
        state['preview'] = ('/previews/'+state['id']+'.png'
                            if state.get('state')=='running' and state.get('phase') in ('upscaling','finalizing')
                            else None)
        if state.get('state') == 'running' and state.get('phase') == 'generating':
            base, _ = self._artifact_paths(state)
            try:
                revision = base.with_name('step-preview.png').stat().st_mtime_ns
            except OSError:
                pass
            else:
                state['preview'] = f"/previews/{state['id']}.png?step={revision}"
        state['profile'] = self.profile
        state['keep_loaded'] = self.keep_loaded
        state['model_loaded'] = self.resident.loaded()
        state['preload_error'] = self.preload_error
        selection_error=self.selection_error()
        state['config_error'] = self.config_error or selection_error
        state['models_ready'] = selection_error is None
        state['enhancer'] = self.enhancer.status()
        return state

    def cancel(self):
        with self.operation_lock:
            with self.lock:
                self.cancel_event.set()
                process, worker = self.process, self.worker
                preserve = not self.closed and self.preload_model and self.resident.loaded()
                if self.job['state'] == 'running':
                    self.job['phase'] = 'cancelling'
            terminate(process)
            if not preserve:
                self.resident.stop()
            if worker and worker is not threading.current_thread():
                worker.join(timeout=40 if preserve else 10)
            if worker and worker.is_alive():
                raise RuntimeError('Cancellation is in progress. Wait for the engine to become available.')
            return self.status()

    def _check_active(self, deadline=None):
        if self.closed or self.cancel_event.is_set():
            raise RuntimeError('Generation canceled.')
        if deadline is not None and time.monotonic() >= deadline:
            raise RuntimeError('The job exceeded the 30-minute limit.')

    def store_reference(self, data):
        if not 33 <= len(data) <= MAX_REFERENCE_BYTES or data[:8] != b'\x89PNG\r\n\x1a\n' or data[8:16] != b'\0\0\0\rIHDR':
            raise ValueError('Upload a valid PNG image up to 25 MB.')
        width, height = struct.unpack('>II', data[16:24])
        if not 0 < width <= 8192 or not 0 < height <= 8192 or width * height > 16777216:
            raise ValueError('Reference images must fit within 8,192 pixels per side and 16 megapixels in total.')
        position, has_pixels, complete = 8, False, False
        while position + 12 <= len(data):
            size = struct.unpack('>I', data[position:position + 4])[0]
            end = position + size + 12
            if end > len(data):
                break
            kind = data[position + 4:position + 8]
            crc = struct.unpack('>I', data[end - 4:end])[0]
            if zlib.crc32(data[position + 4:end - 4]) != crc:
                raise ValueError('The reference image is corrupted.')
            has_pixels |= kind == b'IDAT'
            if kind == b'IEND':
                complete = size == 0 and end == len(data) and has_pixels
                break
            position = end
        if not complete:
            raise ValueError('The reference image is incomplete or invalid.')
        identity = uuid.uuid4().hex
        with self.lock:
            if self.closed:raise ValueError('The app is shutting down.')
            self._prune_temporary_locked()
            with (self.references / (identity + '.png')).open('xb') as output:output.write(data)
            self.reference_seen[identity]=time.time()
        return {'id': identity, 'image': '/references/' + identity + '.png'}

    def start(self, prompt, reference=None, *, seed=None):
        if seed is not None and (type(seed) is not int or not 0 <= seed < 2**31):
            raise ValueError('The seed must be an integer between 0 and 2,147,483,647.')
        with self.operation_lock:
            return self._start(prompt, reference, seed)

    def _start(self, prompt, reference, seed):
        verified=self.library.verifications()
        if any(verified.get(str(path),{}).get('integrity')=='failed' for path in (self.model,self.encoder,self.vae) if path):
            raise ValueError('A component differs from the verified file. Check the Models tab.')
        for component in (self.model, self.encoder, self.vae, self.vision):
            if component and not any(component.resolve().is_relative_to(root) for root in self.library.roots()):
                raise ValueError('The selected component is outside the configured model folders.')
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS or '\0' in prompt:
            raise ValueError(f'Describe the image in up to {MAX_PROMPT_CHARS} characters.')
        if self.enhancer.status()['busy']:
            raise RuntimeError('Wait for prompt enhancement to finish.')
        references = [] if reference is None else [reference] if isinstance(reference, str) else reference
        if not isinstance(references, list) or len(references) > 10:
            raise ValueError('Attach up to 10 reference images.')
        reference_paths = []
        for identity in references:
            if not isinstance(identity, str) or not REFERENCE_ID.fullmatch(identity):
                raise ValueError('Invalid reference image ID. Attach the image again.')
            reference_path = self.references / (identity + '.png')
            if not reference_path.is_file() or reference_path.is_symlink():
                raise ValueError('Reference image not found. Attach it again.')
            reference_paths.append(reference_path)
        with self.lock:
            if self.closed:
                raise RuntimeError('The server is shutting down.')
            if self.job['state'] == 'running':
                raise RuntimeError('An image is already being generated. Wait for it to finish.')
            if reference_paths and not PROFILES[self.profile].get('references',False):
                raise ValueError(PROFILES[self.profile]['label']+' only supports text-to-image generation in this app. Remove the reference images.')
            if reference_paths and PROFILES[self.profile].get('components',{}).get('vision') and (not self.vision or not self.vision.is_file()):
                raise FileNotFoundError('Qwen Image 2.1 requires its Qwen3-VL 8B mmproj vision file for references.')
            if not self.executable.is_file() or not os.access(self.executable, os.X_OK):
                raise FileNotFoundError('The backend has not been built. Run ./build.sh from the project folder.')
            if not self.upscale_executable.is_file() or not os.access(self.upscale_executable, os.X_OK):
                raise FileNotFoundError('Upscaling executable missing: backends/upscayl-ncnn/upscayl-bin.')
            if self.upscale_model.suffix != '.bin':
                raise ValueError('The NCNN upscaler requires a .bin model and its matching .param file.')
            for component in (self.model, self.encoder, self.vae, self.upscale_model, self.upscale_model.with_suffix('.param')):
                if component is not None and not component.is_file():
                    raise FileNotFoundError(f'Component not found: {component.name}. Check that the SSD is mounted and the model folder is correct.')
            model_catalog.validate(self.profile, {'diffusion':self.model,'encoder':self.encoder,'vae':self.vae,'vision':self.vision if reference_paths else None})
            lora=None
            if PROFILES[self.profile].get('lora'):
                lora=self.library.find_lora(self.profile, self.model)
                if not lora:
                    raise FileNotFoundError('Profile LoRA missing. Download it from the Models tab.')
            model_catalog.validate_upscaler(self.upscale_model)
            if self.resident.loaded() and self.resident_policy:
                policy = self.resident_policy
            else:
                policy, _ = hardware.select(hardware.discover(self.executable), HARDWARE_DEFAULTS)
            previous_job=dict(self.job)
            if any(not path.is_file() for path in reference_paths):
                raise ValueError('A reference image was removed. Attach it again.')
            identity = uuid.uuid4().hex
            self.cancel_event.clear()
            geometry = image_geometry(self.resolution,self.aspect_ratio,self.generation_size)
            if seed is None:
                seed = secrets.randbelow(2**31)
            self.job = {'version': 1, 'artifacts_version':2, 'id': identity, 'state': 'running', 'image': None, 'error': None,
                        'started': time.time(), 'seed': seed, 'phase': 'generating',
                        'resolution': self.resolution, 'aspect_ratio':self.aspect_ratio, 'generation_size':self.generation_size, 'hardware': policy, **geometry}
            self.job['settings'] = {'profile':self.profile, 'diffusion':str(self.model), 'encoder':str(self.encoder), 'vae':str(self.vae), 'vision':str(self.vision) if self.vision else '', 'lora':str(lora) if lora else '', 'keep_loaded':self.keep_loaded, 'preload_model':self.preload_model, 'adaptive_weights':self.adaptive_weights, 'upscale_model':str(self.upscale_model), 'sd':dict(self.sd_custom if self.sd_profile=='custom' else SD_DEFAULTS[self.sd_profile])}
            self.job['settings']['sd_profile'] = self.sd_profile
            self.job['reference_ids'] = references
            self.job['model_loaded_at_start'] = self.resident.loaded()
            try:
                self.jobs.save(self.job)
            except OSError as exc:
                self.job=previous_job
                raise explain(exc) from exc
            self._prune_temporary_locked()
            self.worker = threading.Thread(target=self._generate, args=(prompt.strip(), dict(self.job), reference_paths), daemon=True)
            self.worker.start()
            return dict(self.job)

    def _run_stage(self, command, log, env, deadline, label):
        started = time.monotonic()
        with log.open('w', encoding='utf-8') as stream:
            with self.lock:
                self._check_active()
                self.process = spawn(command, cwd=ROOT, env=env, stdout=stream,
                                                stderr=subprocess.STDOUT)
                process = self.process
            try:
                result = process.wait(timeout=max(0.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise RuntimeError('The job exceeded the 30-minute limit. See the log in the logs folder.')
            finally:
                with self.lock:
                    if self.process is process:
                        self.process = None
        if result != 0:
            self._check_active()
            raise native_failure(log,label,result)
        with self.lock:
            self._check_active()
        return round(time.monotonic() - started, 2)

    _validate_image = staticmethod(validate_image)

    def _generate(self, prompt, job, reference=None, resume=False):
        base,upscaled = self._artifact_paths(job)
        output = base.parent/'final.png' if job.get('artifacts_version')==2 else self.outputs/(job['id']+'.png')
        log = self.logs / (job['id'] + '.log')
        upscale_log = self.logs / (job['id'] + '-upscale.log')
        settings = job['settings']
        profile_name = settings['profile']
        base_width, base_height = job['base_width'], job['base_height']
        profile = generation_profile(
            settings.get('sd', SD_DEFAULT), profile_name if profile_name in PROFILES else 'z-image-turbo',
            sd_profile=settings.get('sd_profile'), base_size=(base_width, base_height),
        )
        policy = job['hardware']
        env = hardware.environment()
        if policy['compatibility']:
            env.update(GGML_VK_MAX_NODES_PER_SUBMIT='4', GGML_VK_SERIALIZE_SUBMISSIONS='1')
        device = policy['generator']['ggml']
        components = ['--diffusion-model', settings['diffusion'], '--llm', settings['encoder'], '--vae', settings['vae']]
        is_qwen = profile.get('family') == 'qwen_image21'
        # Qwen Image 2.1 rounds latent dimensions up to multiples of 32.
        # Render on that grid, then crop to the size selected in Settings.
        native_width, native_height = (
            ((base_width + 31) // 32) * 32, ((base_height + 31) // 32) * 32
        ) if is_qwen else (base_width, base_height)
        lora_file = profile.get('lora')
        lora = (Path(settings.get('lora') or (Path(settings['diffusion']).parent / lora_file)) if lora_file else None)
        engine_prompt = f'<lora:{Path(lora_file).stem}:1> {prompt}' if lora_file else prompt
        runtime_backend = f'diffusion={device},te={device},vae={device}'
        weight_args = ['--auto-fit', 'on'] if settings.get('adaptive_weights') else ['--offload-to-cpu']
        memory_args = list(weight_args)
        if profile['mmap']:
            memory_args.append('--mmap')
        if profile['vae_tiling']:
            memory_args.append('--vae-tiling')
            if profile['vae_tile_size']:
                memory_args += ['--vae-tile-size',str(profile['vae_tile_size'])]
        command = [str(self.executable), *components, '-p', engine_prompt,
                   '-W', str(native_width), '-H', str(native_height), '--steps', profile['steps'], '--cfg-scale', profile['cfg'],
                   '--sampling-method', profile['sampler'], '--seed', str(job['seed']), '--backend', runtime_backend,
                   *memory_args, '-o', str(base), *profile['schedule']]
        if lora:
            command.extend(['--lora-model-dir',str(lora.parent)])
            if reference:
                vision = Path(settings['vision'])
                command.extend(['--llm_vision',str(vision)])
        if not is_qwen:
            for path in reference or []:
                command.extend(['-r',str(path)])
        step_preview = base.with_name('step-preview.png')
        command.extend(['--preview', 'proj', '--preview-interval', '1', '--preview-path', str(step_preview)])
        upscale_model = Path(settings['upscale_model'])
        very_light = job.get('generation_size') == 'very-light'
        resized_size = (job['upscaled_width'], job['upscaled_height'])
        final_size = (job['width'], job['height'])
        max_crop = 256 if very_light else 64
        encoded_size = _encoded_size(job)
        intermediate = base.with_name('upscaled-first.png')
        upscale_options = ['-m', str(upscale_model.parent), '-n', upscale_model.stem,
                           '-z', '4', '-t', '128', '-j', '1:1:1', '-g', str(policy['upscaler']['index']), '-f', 'png']
        error = None
        failure = None
        published = False

        def publish_final(source, destination):
            nonlocal published
            with self.lock:
                self._check_active(deadline)
                os.replace(source, destination)
                published = True

        try:
            deadline = time.monotonic() + 1800
            base.parent.mkdir(parents=True,exist_ok=True)
            resident_references = reference or []
            if is_qwen and reference:
                # Originals stay untouched; the vision encoder receives aligned, bounded copies.
                resident_references = []
                for i, source in enumerate(reference):
                    self._check_active(deadline)
                    resident_references.append(prepare_qwen_reference(source, base.parent / f'qwen-reference-{i + 1}.png'))
                command.extend(arg for path in resident_references for arg in ('-r', str(path)))
            if not resume:
                if settings['keep_loaded']:
                    self._check_active(deadline)
                    startup = self._resident_command(settings, policy, profile['mmap'], lora)
                    vision = Path(settings['vision']) if is_qwen and reference else None
                    check = lambda: self._check_active(deadline)
                    started = time.monotonic()
                    self.resident.ensure(startup, self._resident_environment(env, settings, profile['mmap']), ROOT, self.logs / 'resident.log',
                                         vision, check)
                    self.resident_policy = policy
                    self.resident.generate(prompt, job['seed'], profile, resident_references, base, check,
                                           width=native_width, height=native_height,
                                           on_progress=self._native_progress, preview_path=step_preview, lora=lora,
                                           preserve_on_cancel=lambda: settings.get('preload_model',False) and self.cancel_event.is_set() and not self.closed)
                    generation_seconds = round(time.monotonic() - started, 2)
                    log.write_text('Motor persistente: consulte logs/resident.log.\n', encoding='utf-8')
                else:
                    generation_seconds = self._run_stage(command, log, env, deadline, 'image generation')
                if is_qwen and (native_width, native_height) != (base_width, base_height):
                    # Reuse atomic PNG validation/cropping before the normal upscale.
                    # Qwen's extra border (at most 31 px per axis) is not a failed job.
                    finalize(base, base, (native_width, native_height), (base_width, base_height),
                             lambda: self._check_active(deadline), max_crop=31)
            crop_box(resized_size, final_size, max_crop)
            intermediate_valid = False
            upscale_validation = None
            if resume:
                try:
                    upscale_validation = self._validate_image(upscaled, encoded_size)
                    intermediate_valid = True
                except (OSError,RuntimeError):
                    pass
            if not intermediate_valid:
                self._validate_image(base, (base_width, base_height))
                model_catalog.validate_upscaler(upscale_model)
                self._check_active(deadline)
                companion, options = _companion_upscaler(self.upscale_executable)
                chained = very_light and '-2' in options
                native_png = '-P' in options
                encoded_size = final_size if native_png else resized_size
                if resume:
                    upscaled.unlink(missing_ok=True)
                self._publish(phase='upscaling', phase_started=time.time(), upscale_pass=1,
                              upscale_passes=2 if very_light else 1, upscale_chained=chained, native_final_png=native_png,
                              generation_seconds=self.job.get('generation_seconds',0) if resume else generation_seconds)
                upscale_seconds = 0
                next_input = base
                if very_light and not chained:
                    first_command = [str(self.upscale_executable), '-i', str(base), '-o', str(intermediate), *upscale_options]
                    first_log = self.logs / (job['id'] + '-upscale-first.log')
                    upscale_seconds = self._run_stage(first_command, first_log, env, deadline, 'the first upscaling pass')
                    self._validate_image(intermediate, (base_width * 4, base_height * 4))
                    self._publish(upscale_pass=2, phase_started=time.time())
                    next_input = intermediate
                executor = companion if chained or native_png else self.upscale_executable
                upscale_command = [str(executor), '-i', str(next_input), '-o', str(upscaled),
                                   *upscale_options, '-r', f"{job['upscaled_width']}x{job['upscaled_height']}"]
                if chained:
                    upscale_command.append('-2')
                if native_png:
                    upscale_command.extend(['-P', f'{final_size[0]}x{final_size[1]}'])
                upscale_seconds += self._run_stage(upscale_command, upscale_log, env, deadline, 'upscaling')
                upscale_validation = self._validate_image(upscaled, encoded_size)
                self._publish(upscale_seconds=round(upscale_seconds, 2), upscale_pass=2 if very_light else 1)
            self._publish(phase='finalizing')
            finalize(upscaled, output, encoded_size, final_size, lambda: self._check_active(deadline),
                     validation=upscale_validation, max_crop=max_crop, publish=publish_final)
        except (OSError, RuntimeError, ValueError, KeyError, IndexError, MemoryError) as exc:
            failure = explain(exc)
            error = str(failure)
            failed_stage = self.job['phase']
            self.job['failed_stage'] = failed_stage
            upscale_device = policy['upscaler']['index']
            shared_gpu = policy['generator'].get('index', upscale_device) == upscale_device
            if (failed_stage == 'generating' or (failed_stage == 'cancelling' and not self.resident.loaded()) or failure.code in {'ram_exhausted', 'process_killed'}
                    or (shared_gpu and failure.code in {'device_lost', 'vram_exhausted'})):
                self.resident.stop()
            output.unlink(missing_ok=True)
        finally:
            try:
                step_preview.unlink(missing_ok=True)
                if very_light:
                    intermediate.unlink(missing_ok=True)
            except OSError:
                pass
            with self.lock:
                self.process = None
                cancelled = not published and (self.cancel_event.is_set() or self.closed)
                state = 'cancelled' if cancelled else 'error' if error else 'done'
                self.job.update(state=state, phase=state, error=None if cancelled else error,
                                image=None if error or cancelled else '/images/' + job['id'] + '.png', finished=time.time())
                if state=='done':
                    if self.last_preview_id!=job['id']:
                        self.previous_preview_id=self.last_preview_id
                        self.previous_preview_until=time.time()+60
                    self.last_preview_id=job['id']
                self.job['retryable'] = self._recoverable(self.job)
                self.job['error_info'] = {'code':'cancelled' if cancelled else failure.code if failure else 'stage_failed', 'action':failure.action if failure else None, 'message':error, 'stage':self.job.get('failed_stage'), 'retryable':self.job['retryable']} if error or cancelled else None
                try:
                    self.jobs.save(self.job)
                except OSError:
                    # The in-memory result and preview remain usable if a manifest cannot be written.
                    pass
            if state == 'done' and job.get('artifacts_version')==2:
                # Only the preview remains until this app session ends.
                base.unlink(missing_ok=True)
                upscaled.unlink(missing_ok=True)
            with self.lock:self._prune_temporary_locked()

    def close(self):
        self.enhancer.close()
        self.library.close()
        with self.operation_lock:
            with self.lock:
                self.closed = True
            self.cancel()
            self.temporary.cleanup()


def create_server(manager, port=7860):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def send(self, status, body, content_type='application/json; charset=utf-8'):
            if isinstance(body, dict):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            policy = "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
            if self.path.split('?', 1)[0] in ('/sketch.html','/pose.html'):
                policy = policy.replace("frame-ancestors 'none'", "frame-ancestors 'self'")
            if content_type.startswith('image/svg+xml'):
                styles = re.findall(rb'<style[^>]*>(.*?)</style>',body,re.S)
                hashes = ' '.join("'sha256-"+base64.b64encode(hashlib.sha256(style).digest()).decode()+"'" for style in styles)
                policy = "default-src 'none'; style-src "+(hashes or "'none'")+"; frame-ancestors 'none'"
            self.send_header('Content-Security-Policy',policy)
            try:
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # The browser abandoned the request; no response can be sent now.
                self.close_connection = True

        def valid_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error': 'Access is limited to the local address.'})
            path = urlsplit(self.path).path
            if path in ('/api/library','/api/library/progress','/api/library/folders'):
                try:
                    if path=='/api/library':return self.send(200,manager.library_status())
                    if path=='/api/library/progress':return self.send(200,manager.library.snapshot())
                    query=parse_qs(urlsplit(self.path).query)
                    return self.send(200,manager.library.folders(query.get('path',[None])[0]))
                except (ValueError, OSError) as exc:
                    return self.send(400,{'error':str(exc)})
            if path == '/api/status':
                try:
                    missing=[]
                    keep=parse_qs(urlsplit(self.path).query).get('references',[''])[0]
                    if keep:missing=manager.touch_references(keep.split(','))
                except ValueError as exc:return self.send(400,{'error':str(exc)})
                result=manager.status()
                if missing:result['missing_references']=missing
                return self.send(200,result)
            if path == '/api/hardware':
                try:
                    devices = hardware.discover(manager.executable)
                    policy, _ = hardware.select(devices, HARDWARE_DEFAULTS)
                    return self.send(200, {'devices': devices, 'selected': policy})
                except (ValueError, RuntimeError) as exc:
                    return self.send(503, {'error': str(exc)})
            if path == '/api/settings':
                return self.send(200, manager.model_settings())
            if path == '/api/models':
                try:
                    query = parse_qs(urlsplit(self.path).query)
                    roots = json.loads(query['roots'][0]) if 'roots' in query else None
                    return self.send(200,manager.model_catalog(roots))
                except (ValueError,TypeError) as exc:
                    return self.send(400,{'error':str(exc)})
            assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/eyes.js': ('eyes.js', 'text/javascript; charset=utf-8'),
                      '/sketch.html': ('sketch.html', 'text/html; charset=utf-8'),
                      '/pose.html': ('pose.html', 'text/html; charset=utf-8'),
                      '/pose.js': ('pose.js', 'text/javascript; charset=utf-8'),
                      '/pose.css': ('pose.css', 'text/css; charset=utf-8'),
                      '/sketch.js': ('sketch.js', 'text/javascript; charset=utf-8'),
                      '/sketch.css': ('sketch.css', 'text/css; charset=utf-8'),
                      '/mascot.svg': ('mascot.svg','image/svg+xml; charset=utf-8'),
                      '/mascot-waiting.svg': ('mascot-waiting.svg','image/svg+xml; charset=utf-8'),
                      '/mascot-generating.svg': ('mascot-generating.svg','image/svg+xml; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if path in assets:
                name, mime = assets[path]
                return self.send(200, (WEB / name).read_bytes(), mime)
            if path.startswith('/images/') and IMAGE_NAME.fullmatch(path[8:]):
                data=manager.asset_bytes(path[8:-4])
                if data is not None:return self.send(200,data,'image/png')
            if path.startswith('/previews/') and IMAGE_NAME.fullmatch(path[10:]):
                data=manager.base_preview_bytes(path[10:-4])
                if data is not None:return self.send(200,data,'image/png')
            if path.startswith('/references/') and IMAGE_NAME.fullmatch(path[12:]):
                data=manager.asset_bytes(path[12:-4],reference=True)
                if data is not None:return self.send(200,data,'image/png')
            return self.send(404, {'error': 'Not found.'})

        def do_POST(self):
            if not self.valid_host() or self.headers.get('Origin', 'http://' + self.headers.get('Host', '')) != 'http://' + self.headers.get('Host', ''):
                return self.send(403, {'error': 'Origin not allowed.'})
            if self.path == '/api/enhance/cancel':
                return self.send(200,manager.enhancer.cancel_current())
            if self.path == '/api/cancel':
                try:
                    return self.send(200, manager.cancel())
                except RuntimeError as exc:
                    return self.send(409, {'error': str(exc)})
            if self.path == '/api/reference':
                if self.headers.get_content_type() != 'image/png':
                    return self.send(415, {'error': 'Upload the reference image as image/png.'})
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= MAX_REFERENCE_BYTES:
                        return self.send(413, {'error': 'The reference image must be 25 MB or smaller.'})
                    self.connection.settimeout(30)
                    data = self.rfile.read(length)
                    if len(data) != length:
                        raise ValueError('The reference image upload was incomplete.')
                    return self.send(201, manager.store_reference(data))
                except ValueError as exc:
                    return self.send(400, {'error': str(exc)})
                except OSError as exc:
                    return self.send(500, {'error': str(explain(exc))})
            retry = re.fullmatch(r'/api/jobs/([0-9a-f]{32})/retry-finalize', self.path)
            if retry:
                try:
                    return self.send(202, manager.retry_finalize(retry[1]))
                except ValueError as exc:
                    return self.send(400, {'error':str(exc)})
                except RuntimeError as exc:
                    return self.send(409, {'error':str(exc)})
            if self.path not in {'/api/generate', '/api/models', '/api/settings','/api/library','/api/enhance','/api/references/release'}:
                return self.send(404, {'error': 'Not found.'})
            if self.headers.get_content_type() != 'application/json':
                return self.send(415, {'error': 'Send the request as application/json.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 65536:
                    raise ValueError('The request is empty or too large.')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('Invalid request.')
                if self.path=='/api/references/release':return self.send(200,manager.release_references(body.get('ids')))
                if self.path=='/api/enhance':
                    with manager.operation_lock:
                        if manager.status()['state']=='running':raise RuntimeError('Wait for image generation to finish before enhancing the prompt.')
                        iterator=manager.enhancer.stream(body.get('prompt'),body.get('editing',False),mode=body.get('mode','simple'))
                        first=next(iterator)
                    self.send_response(200)
                    self.send_header('Content-Type','application/x-ndjson; charset=utf-8')
                    self.send_header('Cache-Control','no-store')
                    self.send_header('X-Content-Type-Options','nosniff')
                    self.send_header('Connection','close')
                    self.end_headers();self.close_connection=True
                    def emit(event):
                        self.wfile.write((json.dumps(event,ensure_ascii=False)+'\n').encode('utf-8'));self.wfile.flush()
                    try:
                        emit(first)
                        for event in iterator:emit(event)
                    except (BrokenPipeError,ConnectionResetError):pass
                    except Exception as exc:
                        try:emit({'error':str(exc)})
                        except OSError:pass
                    finally:iterator.close()
                    return
                if self.path=='/api/library':
                    return self.send(200,manager.library_action(body))
                if self.path in {'/api/models', '/api/settings'}:
                    return self.send(200, manager.configure(body, persist=True))
                return self.send(202, manager.start(body.get('prompt'), body.get('reference'), seed=body.get('seed')))
            except (ValueError, UnicodeError) as exc:
                return self.send(400, {'error': str(exc)})
            except RuntimeError as exc:
                return self.send(409, {'error': str(exc)})
            except FileNotFoundError as exc:
                return self.send(503, {'error': str(exc)})
            except OSError as exc:
                return self.send(500, {'error': str(explain(exc))})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser(description='popAI local image generation')
    parser.add_argument('--port', type=int, default=7860)
    parser.add_argument('--model-dir', type=Path, action='append', help='Model folder. Repeat this option to add more folders.')
    parser.add_argument('--upscale-model', type=Path, default=DEFAULT_UPSCALER,
                        help='Real-ESRGAN 4× NCNN .bin weights with the .param file in the same folder')
    args = parser.parse_args()
    store = SettingsStore(ROOT)
    store.check_writable()
    configuration_error = None
    try:
        configuration = store.load()
    except (ValueError, OSError) as exc:
        configuration = {}
        configuration_error = f'Could not read the saved settings: {exc}'
    roots = [str(p) for p in (args.model_dir or configuration.get('model_roots', [str(DEFAULT_MODEL_DIR)]))]
    manager = GenerationManager(ROOT / 'backends/stable-diffusion.cpp/build/bin/sd-cli',
                                roots[0], ROOT / 'outputs', ROOT / 'logs', upscale_model=args.upscale_model,
                                model_roots=roots, store=store)
    manager.config_error = configuration_error
    if configuration:
        try:
            if configuration.get('profile') not in PROFILES:
                configuration['profile'] = 'z-image-turbo'
            configuration['model_roots'] = [str(p) for p in roots]
            manager.configure(configuration, allow_missing=True)
        except (ValueError, OSError) as exc:
            manager.config_error = f'Check the saved settings. Details: {exc}'
    server = create_server(manager, args.port)
    # Enhance loads its Vulkan model only when requested; never preload at startup.
    def stop_server(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_server)
    print(f'popAI: http://127.0.0.1:{server.server_port} (press Ctrl+C to stop).', flush=True)
    try:
        if manager.preload_model:
            print('Preparing selected model in memory…', flush=True)
            if manager.preload_selected_model():
                print('Selected model ready.', flush=True)
            elif manager.preload_error:
                print(f'Model preload failed: {manager.preload_error}', flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        manager.close()
        server.server_close()


if __name__ == '__main__':
    main()
