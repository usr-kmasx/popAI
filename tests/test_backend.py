import json
import os
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from app_config import SettingsStore
from catalog import MODEL_DEFAULTS, SD_DEFAULTS, generation_profile
import urllib.error
import urllib.request
import zlib
from pathlib import Path

from server import GenerationManager, create_server


def reference_png():
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',8,8,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x20\x40\x60'*8)*8))+chunk(b'IEND',b'')


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.model_dir = self.root / 'flux'
        self.model_dir.mkdir()
        self.model = self.model_dir / 'z_image_turbo-Q8_0.gguf'
        self.encoder = self.model_dir / 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
        self.vae = self.model_dir / 'ae.safetensors'
        for component in (self.model, self.encoder, self.vae):
            component.touch()
        self.upscaler = self.root / 'upscale.bin'
        self.upscaler.write_bytes(b'x'*2048)
        self.upscaler.with_suffix('.param').write_text('7767517\n1 1\nInput input 0 1 in\n')
        self.executable = self.root / 'fake-sd'
        self.executable.write_text('''#!/usr/bin/env python3
import json, os, pathlib, struct, sys, time, zlib
args = sys.argv[1:]
base = pathlib.Path(__file__)
upscale = '-i' in args
if upscale:
    prompt = base.with_suffix('.prompt').read_text()
    previous_pid = int(base.with_suffix('.generation-pid').read_text())
    try: os.kill(previous_pid, 0)
    except ProcessLookupError: pass
    else: sys.exit(80)
else:
    prompt = args[args.index('-p')+1]
    base.with_suffix('.prompt').write_text(prompt)
    base.with_suffix('.generation-pid').write_text(str(os.getpid()))
    refs = [pathlib.Path(args[i+1]) for i,key in enumerate(args) if key=='-r']
    base.with_suffix('.refs').write_text(json.dumps([
        {'path':str(path),'dimensions':list(struct.unpack('>II',path.read_bytes()[16:24]))}
        for path in refs]))
with base.with_suffix('.calls').open('a') as trace: trace.write(json.dumps(args)+'\\n')
base.with_suffix('.upscale-args' if upscale else '.args').write_text(json.dumps(args))
pathlib.Path(__file__).with_suffix('.env').write_text(json.dumps({key: os.environ.get(key) for key in ['GGML_VK_MAX_NODES_PER_SUBMIT', 'GGML_VK_SERIALIZE_SUBMISSIONS']}))
if prompt == 'device_lost':
    print('[E] ggml_vulkan: device lost on Vulkan0: ErrorDeviceLost', flush=True)
    sys.exit(1)
if prompt == 'block':
    pathlib.Path(__file__).with_suffix('.pid').write_text(str(os.getpid()))
    time.sleep(30)
if prompt == 'slow': time.sleep(0.3)
if upscale and prompt == 'slow_upscale': time.sleep(1)
if upscale and prompt == 'fail_upscale': sys.exit(2)
if prompt == 'fail': sys.exit(2)
if prompt == 'missing': sys.exit(0)
out = pathlib.Path(args[args.index('-o')+1])
def chunk(name, data):
    return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))
if '<lora:chatrlabs-omni-turbo-8step-fp32:1>' in prompt:
    if upscale:
        width,height = map(int,args[args.index('-r')+1].split('x'))
    else:
        width,height = int(args[args.index('-W')+1]),int(args[args.index('-H')+1])
else:
    width,height = (1920,1088) if upscale and prompt != 'unscaled_upscale' else (960,544)
png = b'\\x89PNG\\r\\n\\x1a\\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
png += chunk(b'IDAT', zlib.compress((b'\\0' + bytes([16, 32, 48])*width)*height)) + chunk(b'IEND', b'')
out.write_bytes(png if prompt != 'invalid' else b'broken')
''')
        self.executable.chmod(0o755)
        self.manager = GenerationManager(self.executable, self.model_dir, upscale_model=self.upscaler,store=SettingsStore(self.root),keep_loaded=False)
        self.manager.upscale_executable = self.executable
        self.patches = [patch('server.model_catalog.validate'),patch('server.hardware.discover',return_value=[dict(index=0,name='RADV POLARIS10',type=2,total=8*1024**3,free=7*1024**3,usable=True,ggml='Vulkan0')])]
        for item in self.patches: item.start()

    def tearDown(self):
        self.manager.close()
        for item in self.patches: item.stop()
        self.temp.cleanup()

    def wait_job(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = self.manager.status()
            if state['state'] != 'running':
                return state
            time.sleep(0.02)
        self.fail('generation did not finish')

    def test_rejects_empty_and_non_text_prompt(self):
        for prompt in ('   ', None, 123, 'a'*16001, 'landscape\0test'):
            with self.assertRaises(ValueError):
                self.manager.start(prompt)

    def test_prompt_is_literal_and_result_has_expected_dimensions(self):
        prompt = 'a landscape; $(touch UNEXPECTED) `echo test` "á"\nsecond line'
        self.manager.start(prompt)
        state = self.wait_job()
        self.assertEqual(state['state'], 'done')
        args = json.loads(self.executable.with_suffix('.args').read_text())
        self.assertEqual(args[args.index('-p')+1], prompt)
        self.assertEqual(args[args.index('--diffusion-model')+1], str(self.model))
        self.assertEqual(args[args.index('--llm')+1], str(self.encoder))
        self.assertEqual(args[args.index('--vae')+1], str(self.vae))
        self.assertNotIn('-m', args)
        self.assertNotIn('--type', args)
        self.assertNotIn('--sigmas', args)
        self.assertNotIn('--model-args', args)
        self.assertNotIn('--scheduler', args)
        self.assertNotIn('--max-vram', args)
        self.assertNotIn('--params-backend', args)
        self.assertEqual(args[args.index('--backend')+1], 'diffusion=Vulkan0,te=Vulkan0,vae=Vulkan0')
        self.assertNotIn('-n', args)
        self.assertEqual(args[args.index('--cfg-scale')+1], '1.0')
        self.assertEqual(args[args.index('--steps')+1], '9')
        self.assertEqual(args[args.index('-W')+1], '960')
        self.assertEqual(args[args.index('-H')+1], '544')
        self.assertIn('--offload-to-cpu', args)
        self.assertIn('--vae-tiling', args)
        environment = json.loads(self.executable.with_suffix('.env').read_text())
        self.assertEqual(environment['GGML_VK_MAX_NODES_PER_SUBMIT'], '4')
        self.assertEqual(environment['GGML_VK_SERIALIZE_SUBMISSIONS'], '1')
        output = self.manager.image_path(state['id'])
        self.assertEqual(struct.unpack('>II', output.read_bytes()[16:24]), (1920, 1080))
        up_args = json.loads(self.executable.with_suffix('.upscale-args').read_text())
        self.assertEqual(up_args[up_args.index('-m')+1], str(self.upscaler.parent))
        self.assertEqual(up_args[up_args.index('-n')+1], self.upscaler.stem)
        self.assertNotIn('--diffusion-model', up_args)
        self.assertNotIn('--llm', up_args)
        self.assertNotIn('--vae', up_args)
        self.assertEqual(up_args[up_args.index('-i')+1], args[args.index('-o')+1])
        self.assertEqual(len(self.executable.with_suffix('.calls').read_text().splitlines()), 2)

    def test_startup_preload_is_optional_persisted_and_reuses_resident_command(self):
        self.manager.keep_loaded = True
        self.assertFalse(self.manager.preload_model)
        with patch.object(self.manager.resident,'ensure') as ensure:
            self.assertFalse(self.manager.preload_selected_model())
            ensure.assert_not_called()
        settings = {**self.manager.model_settings(),'preload_model':True}
        self.manager.configure(settings,persist=True,allow_missing=True)
        self.assertIs(self.manager.store.load()['preload_model'],True)
        self.assertIs(self.manager.model_settings()['preload_model'],True)
        self.manager.preload_model=False
        self.manager.configure(self.manager.store.load(),allow_missing=True)
        self.assertTrue(self.manager.preload_model)
        self.manager.executable.with_name('sd-server').touch()
        previous_job=dict(self.manager.job)
        with patch.object(self.manager.resident,'ensure') as ensure, patch.object(self.manager.resident,'generate') as generate:
            self.assertTrue(self.manager.preload_selected_model())
            ensure.assert_called_once()
            generate.assert_not_called()
            command,env,root,log,vision,check=ensure.call_args.args
            self.assertIn('--offload-to-cpu',command)
            self.assertIn('--eager-load',command)
            self.assertEqual(env.get('SD_MMAP_FLAGS'),'populate')
            self.assertNotIn('--eager-load',self.manager._resident_command({**self.manager.model_settings(),'preload_model':False},self.manager.resident_policy,True))
            self.assertNotIn('SD_MMAP_FLAGS',self.manager._resident_environment({}, {'preload_model':False},True))
            self.assertEqual(command[command.index('--diffusion-model')+1],str(self.manager.model))
            self.assertEqual(command,self.manager._resident_command(self.manager.model_settings(),self.manager.resident_policy,
                              self.manager.model_settings()['sd_defaults'][self.manager.sd_profile]['mmap']))
            self.assertIsNone(vision)
            check()
        self.assertEqual(self.manager.job,previous_job)
        with patch.object(self.manager.resident,'ensure',side_effect=RuntimeError('Test load failure')), patch.object(self.manager.resident,'stop') as stop:
            self.assertFalse(self.manager.preload_selected_model())
            stop.assert_called_once()
            self.assertIn('Test load failure',self.manager.preload_error)
        with self.assertRaises(ValueError):
            self.manager.configure({**settings,'preload_model':'true'},persist=True,allow_missing=True)
        self.assertTrue(self.manager.store.load()['preload_model'])

    def test_prompt_processing_persists_and_rejects_invalid_values(self):
        expected = {'corrector':False,'enhancer':True,'lite':True}
        settings = {**self.manager.model_settings(),'prompt_processing':expected}
        self.manager.configure(settings,persist=True,allow_missing=True)
        self.assertEqual(self.manager.store.load()['prompt_processing'],expected)
        self.assertEqual(self.manager.model_settings()['prompt_processing'],expected)
        self.assertEqual(self.manager.status()['enhancer']['options'],expected)
        self.assertEqual(self.manager.enhancer.context_size,4096)
        with self.assertRaises(ValueError):
            self.manager.configure({**settings,'prompt_processing':{'lite':'true'}},persist=True,allow_missing=True)
        self.assertEqual(self.manager.store.load()['prompt_processing'],expected)
        self.manager.enhancer.options = {'corrector':True,'enhancer':True,'lite':False}
        self.manager.configure(self.manager.store.load(),allow_missing=True)
        self.assertEqual(self.manager.enhancer.options,expected)

    def test_chatrlabs_experimental_profile_uses_eight_steps_and_turbo_lora(self):
        from catalog import PROFILES, PROFILE_FILES
        from model_catalog import diffusion_profile
        self.assertNotIn('experimental', PROFILES['qwen-image21-experimental'])
        self.assertIn('qwen-image21-experimental', MODEL_DEFAULTS,
                      'Qwen must be part of the three remaining popAI model sets')
        self.assertEqual(len(MODEL_DEFAULTS), 3)
        self.assertEqual(set(MODEL_DEFAULTS['qwen-image21-experimental']),
                         {'diffusion', 'encoder', 'vae', 'vision'})
        manifest=json.loads((Path(__file__).resolve().parents[1]/'model-downloads.json').read_text())
        self.assertEqual(set(manifest),set(MODEL_DEFAULTS))
        self.assertEqual({item['role'] for item in manifest['qwen-image21-experimental']},
                         {'diffusion','encoder','vae','vision','lora'})
        self.assertEqual(len(manifest['qwen-image21-experimental']),5)
        files = PROFILE_FILES['qwen-image21-experimental']
        for name in files.values():
            (self.model_dir / name).touch()
        (self.model_dir / 'chatrlabs-omni-turbo-8step-fp32.safetensors').touch()
        settings = {**self.manager.model_settings(),
                    'profile':'qwen-image21-experimental',
                    'sd_profile':'qwen-image21-experimental',
                    **{role:str(self.model_dir/name) for role,name in files.items()}}
        self.manager.configure(settings, persist=True)
        self.assertEqual(self.manager.store.load()['sd_profile'],'qwen-image21-experimental')
        self.manager.start('Red boat at sunrise',seed=12)
        self.assertEqual(self.wait_job()['state'],'done')
        args = json.loads(self.executable.with_suffix('.args').read_text())
        self.assertEqual(args[args.index('--steps')+1],'8')
        self.assertEqual(args[args.index('--cfg-scale')+1],'1.0')
        self.assertEqual(args[args.index('--scheduler')+1],'simple')
        self.assertEqual(args[args.index('--lora-model-dir')+1],str(self.model_dir))
        self.assertEqual(args[args.index('-p')+1],
                         '<lora:chatrlabs-omni-turbo-8step-fp32:1> Red boat at sunrise')
        self.assertEqual(args[args.index('--diffusion-model')+1],str(self.model_dir/files['diffusion']))
        self.assertEqual(args[args.index('--llm')+1],str(self.model_dir/files['encoder']))
        self.assertEqual(args[args.index('--vae')+1],str(self.model_dir/files['vae']))
        self.assertEqual(self.manager.model_settings()['profile'],'qwen-image21-experimental')

    def test_qwen_fast_four_steps_preserves_eight_step_settings(self):
        from catalog import SD_DEFAULTS, SD_PROFILE_FAMILIES, generation_profile
        normal=SD_DEFAULTS['qwen-image21-experimental']
        experimental=SD_DEFAULTS['qwen-image21-4']
        self.assertEqual(SD_PROFILE_FAMILIES['qwen-image21-4'],
                         'qwen-image21-experimental')
        self.assertEqual(experimental['steps'],4)
        self.assertEqual(normal['steps'],8)
        self.assertEqual({k:v for k,v in experimental.items() if k!='steps'},
                         {k:v for k,v in normal.items() if k!='steps'})
        base=generation_profile(normal,'qwen-image21-experimental',
                                sd_profile='qwen-image21-experimental',base_size=(768,448))
        test=generation_profile(experimental,'qwen-image21-experimental',
                                sd_profile='qwen-image21-4',base_size=(768,448))
        self.assertEqual(base['schedule'],test['schedule'])
        self.assertEqual(base['lora'],test['lora'])
        self.assertEqual(base['cfg'],test['cfg'])
        self.assertEqual(test['steps'],'4')
        self.assertEqual(test['schedule'],['--scheduler','simple'])
        self.assertNotIn('qwen-image21-4-experimental', SD_DEFAULTS)

    def test_legacy_qwen_four_step_profile_migrates_to_fast(self):
        from catalog import PROFILE_FILES
        files=PROFILE_FILES['qwen-image21-experimental']
        for name in files.values():
            (self.model_dir/name).touch()
        (self.model_dir/'chatrlabs-omni-turbo-8step-fp32.safetensors').touch()
        settings={**self.manager.model_settings(),
                  'profile':'qwen-image21-experimental',
                  'sd_profile':'qwen-image21-4-experimental',
                  **{role:str(self.model_dir/name) for role,name in files.items()}}
        result=self.manager.configure(settings,persist=True)
        self.assertEqual(result['sd_profile'],'qwen-image21-4')
        self.assertEqual(self.manager.store.load()['sd_profile'],'qwen-image21-4')
        self.manager.start('Test fast Qwen',seed=20261122)
        self.assertEqual(self.wait_job()['state'],'done')
        args=json.loads(self.executable.with_suffix('.args').read_text())
        self.assertEqual(args[args.index('--steps')+1],'4')
        self.assertEqual(args[args.index('--scheduler')+1],'simple')
        self.assertEqual(args[args.index('--seed')+1],'20261122')
        self.assertEqual(args[args.index('--lora-model-dir')+1],str(self.model_dir))

    def test_official_qwen_library_detects_all_five_dependencies(self):
        from catalog import PROFILE_FILES
        files=PROFILE_FILES['qwen-image21-experimental']
        for name in files.values():
            (self.model_dir/name).touch()
        lora=self.model_dir/'chatrlabs-omni-turbo-8step-fp32.safetensors'
        lora.touch()
        settings={**self.manager.model_settings(),
                  'profile':'qwen-image21-experimental',
                  'sd_profile':'qwen-image21-experimental',
                  **{role:str(self.model_dir/name) for role,name in files.items()}}
        self.manager.configure(settings)
        families={
            'diffusion':'qwen_image21','encoder':'qwen3vl-8b',
            'vae':'qwen','vision':'qwen3vl-8b',
        }
        components={str(self.model_dir/name):{'role':role,'family':families[role]}
                    for role,name in files.items()}
        with patch.object(self.manager,'_catalog_components',return_value=components):
            library=self.manager.library_status()
            self.assertEqual(len(library['sets']),3)
            q=library['sets']['qwen-image21-experimental']
            self.assertTrue(q['complete'])
            self.assertEqual(set(q['present']),{'diffusion','encoder','vae','vision','lora'})
            self.assertEqual(q['present']['lora'],str(lora))
            self.assertEqual(q['download_bytes'],0)
            self.assertTrue(all(len(entry['roles'])==3 for family,entry in
                                library['sets'].items() if family!='qwen-image21-experimental'))
            lora.unlink()
            q=self.manager.library_status()['sets']['qwen-image21-experimental']
            self.assertFalse(q['complete'])
            self.assertNotIn('lora',q['present'])
            self.assertEqual(q['download_bytes'],671148320)
            with self.assertRaisesRegex(ValueError,'LoRA'):
                self.manager.library_action({'action':'verify',
                    'families':['qwen-image21-experimental'],
                    'components':{'qwen-image21-experimental':{
                        role:q['present'][role] for role in ('diffusion','encoder','vae','vision')}}})

    def test_downloads_group_all_weights_by_model_in_one_named_folder(self):
        from model_library import MODEL_SET_DIRECTORIES
        from copy import deepcopy
        self.manager.library.configure(str(self.model_dir), 'destination')
        original=self.manager.library.manifest
        self.manager.library.manifest=deepcopy(original)
        for parts in self.manager.library.manifest.values():
            for item in parts:
                item['size']=1  # No large downloads or disk-space requirements in this test.
        captured=[]
        try:
            with patch.object(self.manager.library, '_run',
                              side_effect=lambda action,tasks: captured.extend(tasks)):
                families=list(MODEL_SET_DIRECTORIES)
                self.manager.library.start('download',families,{family:{} for family in families})
                self.manager.library.worker.join(timeout=3)
            self.assertEqual(len(captured),11)
            for family,component,target in captured:
                self.assertEqual(target.parent,self.model_dir/MODEL_SET_DIRECTORIES[family])
                self.assertEqual(target.name,component['filename'])
            qwen=[(item['role'],target.parent) for family,item,target in captured
                  if family=='qwen-image21-experimental']
            self.assertEqual({role for role,_ in qwen},
                             {'diffusion','encoder','vae','vision','lora'})
            self.assertEqual(len({str(folder) for _,folder in qwen}),1)
        finally:
            self.manager.library.manifest=original

    def test_imported_qwen_uses_lora_from_organized_folder_without_moving_generator(self):
        from catalog import PROFILE_FILES
        files=PROFILE_FILES['qwen-image21-experimental']
        for name in files.values():
            (self.model_dir/name).touch()
        package=self.model_dir/'Qwen Image 2.1'
        package.mkdir()
        lora=package/'chatrlabs-omni-turbo-8step-fp32.safetensors'
        lora.touch()
        settings={**self.manager.model_settings(),
                  'profile':'qwen-image21-experimental',
                  'sd_profile':'qwen-image21-experimental',
                  **{role:str(self.model_dir/name) for role,name in files.items()}}
        self.manager.configure(settings,persist=True)
        families={'diffusion':'qwen_image21','encoder':'qwen3vl-8b',
                  'vae':'qwen','vision':'qwen3vl-8b'}
        components={str(self.model_dir/name):{'role':role,'family':families[role]}
                    for role,name in files.items()}
        with patch.object(self.manager,'_catalog_components',return_value=components):
            found=self.manager.library_status()['sets']['qwen-image21-experimental']
        self.assertTrue(found['complete'])
        self.assertEqual(found['present']['lora'],str(lora))
        self.manager.start('Organized folders',seed=15)
        result=self.wait_job()
        self.assertEqual(result['state'],'done',result.get('error'))
        arguments=json.loads(self.executable.with_suffix('.args').read_text())
        self.assertEqual(arguments[arguments.index('--lora-model-dir')+1],str(package))
        self.assertEqual(arguments[arguments.index('--diffusion-model')+1],
                         str(self.model_dir/files['diffusion']))
        self.assertTrue(lora.is_file())
        self.assertTrue((self.model_dir/files['diffusion']).is_file())
        self.assertEqual(self.manager.store.load()['sd_profile'],'qwen-image21-experimental')

    def test_qwen_partial_download_queues_only_missing_lora_in_named_folder(self):
        from catalog import PROFILE_FILES
        from copy import deepcopy
        files=PROFILE_FILES['qwen-image21-experimental']
        for name in files.values():
            (self.model_dir/name).touch()
        self.manager.library.configure(str(self.model_dir),'destination')
        settings={**self.manager.model_settings(),
                  'profile':'qwen-image21-experimental',
                  'sd_profile':'qwen-image21-experimental',
                  **{role:str(self.model_dir/name) for role,name in files.items()}}
        self.manager.configure(settings)
        components={str(self.model_dir/name):{'role':role,'family':family}
                    for role,name,family in [
                        ('diffusion',files['diffusion'],'qwen_image21'),
                        ('encoder',files['encoder'],'qwen3vl-8b'),
                        ('vae',files['vae'],'qwen'),
                        ('vision',files['vision'],'qwen3vl-8b')]}
        with patch.object(self.manager,'_catalog_components',return_value=components):
            q=self.manager.library_status()['sets']['qwen-image21-experimental']
            self.assertEqual(set(q['present']),{'diffusion','encoder','vae','vision'})
            self.assertFalse(q['complete'])
            self.assertEqual(q['download_bytes'],671148320)
            self.assertIn('Turbo LoRA',self.manager.selection_error())
            originals=self.manager.library.manifest
            temporary=deepcopy(originals)
            for c in temporary['qwen-image21-experimental']:
                c['size']=1
            self.manager.library.manifest=temporary
            captured=[]
            try:
                with patch.object(self.manager.library,'_run',
                                  side_effect=lambda action,tasks:captured.extend(tasks)):
                    self.manager.library.start('download',['qwen-image21-experimental'],
                                               {'qwen-image21-experimental':q['present']})
                    self.manager.library.worker.join(timeout=3)
                self.assertEqual(len(captured),1)
                self.assertEqual(captured[0][1]['role'],'lora')
                self.assertEqual(captured[0][2].parent,self.model_dir/'Qwen Image 2.1')
            finally:
                self.manager.library.manifest=originals

    def test_existing_partial_download_resumes_in_legacy_folder(self):
        from model_library import MODEL_SET_DIRECTORIES
        self.manager.library.configure(str(self.model_dir),'destination')
        family='qwen-image21-experimental'
        component=next(item for item in self.manager.library.manifest[family]
                       if item['role']=='lora')
        legacy=self.model_dir/family/component['filename']
        legacy.parent.mkdir()
        legacy.with_name(legacy.name+'.part').write_bytes(b'partial download')
        self.assertEqual(self.manager.library.download_target(family,component),legacy)
        organized=self.model_dir/MODEL_SET_DIRECTORIES[family]/component['filename']
        organized.parent.mkdir()
        organized.with_name(organized.name+'.part').write_bytes(b'new partial')
        self.assertEqual(self.manager.library.download_target(family,component),organized)
        self.assertEqual(legacy.with_name(legacy.name+'.part').read_bytes(),b'partial download')

    def test_chatrlabs_experimental_reference_loading_and_multiple_images(self):
        from catalog import PROFILE_FILES
        files = PROFILE_FILES['qwen-image21-experimental']
        for name in files.values():
            (self.model_dir / name).touch()
        (self.model_dir / 'chatrlabs-omni-turbo-8step-fp32.safetensors').touch()
        settings = {**self.manager.model_settings(),
                    'profile':'qwen-image21-experimental',
                    'sd_profile':'qwen-image21-experimental',
                    **{role:str(self.model_dir/name) for role,name in files.items()}}
        self.manager.configure(settings, persist=True)
        refs = [self.manager.store_reference(reference_png()) for _ in range(2)]
        self.manager.start('Preserve image 1, use the colors of image 2',
                           [r['id'] for r in refs], seed=17)
        state = self.wait_job()
        self.assertEqual(state['state'],'done',state.get('error'))
        args=json.loads(self.executable.with_suffix('.args').read_text())
        self.assertEqual(args.count('-r'),2)
        self.assertEqual(args[args.index('--llm_vision')+1],str(self.model_dir/files['vision']))
        self.assertEqual(args[args.index('--backend')+1],'diffusion=Vulkan0,te=Vulkan0,vae=Vulkan0')
        self.assertIn('--offload-to-cpu',args)
        self.assertNotIn('--max-vram',args)
        self.assertEqual(args[args.index('--lora-model-dir')+1],str(self.model_dir))
        for i in range(2):
            tmp=Path(args[[pos for pos,key in enumerate(args) if key=='-r'][i]+1])
            observed=json.loads(self.executable.with_suffix('.refs').read_text())[i]
            self.assertEqual(observed, {'path':str(tmp),'dimensions':[32,32]})
            self.assertFalse(tmp.exists(), 'derived reference survived generation')
            self.assertNotEqual(tmp,self.manager.references / (refs[i]['id']+'.png'))
            self.assertEqual(struct.unpack('>II',(self.manager.references / (refs[i]['id']+'.png')).read_bytes()[16:24]),(8,8))

    def test_chatrlabs_references_require_a_vision_file(self):
        from catalog import PROFILE_FILES
        files=PROFILE_FILES['qwen-image21-experimental']
        for role,name in files.items():
            if role!='vision':(self.model_dir / name).touch()
        (self.model_dir / 'chatrlabs-omni-turbo-8step-fp32.safetensors').touch()
        settings={**self.manager.model_settings(),
                  'profile':'qwen-image21-experimental','sd_profile':'qwen-image21-experimental',
                  **{role:str(self.model_dir/name) for role,name in files.items() if role!='vision'}, 'vision':''}
        self.manager.configure(settings,persist=False)
        ref=self.manager.store_reference(reference_png())
        with self.assertRaisesRegex(FileNotFoundError,'mmproj'):
            self.manager.start('Edit the attached image',[ref['id']])

    def test_qwen_experimental_light_uses_native_32_grid_then_exact_requested_crop(self):
        from catalog import PROFILE_FILES
        files = PROFILE_FILES['qwen-image21-experimental']
        for name in files.values():
            (self.model_dir / name).touch()
        (self.model_dir / 'chatrlabs-omni-turbo-8step-fp32.safetensors').touch()
        settings = {**self.manager.model_settings(),
                    'profile':'qwen-image21-experimental',
                    'sd_profile':'qwen-image21-experimental',
                    'generation_size':'light',
                    **{role:str(self.model_dir / name) for role,name in files.items()}}
        self.manager.configure(settings, persist=True)
        from image_pipeline import finalize as native_finalize
        with patch('server.finalize',wraps=native_finalize) as finalize_checked:
            self.manager.start('Red boat in a river',seed=13)
            job = self.wait_job()
        self.assertEqual(job['state'],'done',job.get('error'))
        self.assertEqual((job['base_width'],job['base_height']),(768,432))
        args = json.loads(self.executable.with_suffix('.args').read_text())
        self.assertEqual((int(args[args.index('-W')+1]),int(args[args.index('-H')+1])),(768,448))
        crop_calls = [call.args for call in finalize_checked.call_args_list
                      if call.args[0] == call.args[1]]
        self.assertTrue(any(args[2:4] == ((768,448),(768,432)) for args in crop_calls))
        final = self.manager.image_path(job['id'])
        self.assertEqual(struct.unpack('>II',final.read_bytes()[16:24]),(1920,1080))

    def test_zimage_presets_keep_the_requested_seed_and_use_their_own_schedule(self):
        settings = self.manager.model_settings()
        presets = [
            ('z-image-4', '4', [1.0, .9001200199127197, .62, .22, 0.0]),
            ('z-image-5', '5', [1.0, .9001200199127197, .7503749132156372, .5009990334510803, .22, 0.0]),
            ('default', '9', None),
            ('custom', '9', None),
        ]
        for preset, steps, sigmas in presets:
            with self.subTest(preset=preset):
                self.manager.configure({**settings, 'sd_profile': preset}, persist=True)
                self.assertEqual(self.manager.store.load()['sd_profile'], preset)
                self.manager.start('Rio com dois pescadores', seed=0)
                self.assertEqual(self.wait_job()['state'], 'done')
                args = json.loads(self.executable.with_suffix('.args').read_text())
                self.assertEqual(args[args.index('--seed') + 1], '0')
                self.assertEqual(args[args.index('--steps') + 1], steps)
                if sigmas is None:
                    self.assertNotIn('--sigmas', args)
                else:
                    self.assertEqual([float(v) for v in args[args.index('--sigmas') + 1].split(',')], sigmas)
        for invalid in (-1, 2**31, True, 2.5, '17'):
            with self.subTest(seed=invalid), self.assertRaises(ValueError):
                self.manager.start('Rio com dois pescadores', seed=invalid)

    def test_previous_five_step_setting_selects_the_new_preset(self):
        settings = {**self.manager.model_settings(), 'experimental_five_steps': True}
        configured = self.manager.configure(settings, persist=True)
        self.assertEqual(configured['sd_profile'], 'z-image-5')
        self.assertNotIn('experimental_five_steps', self.manager.store.load())

    def test_klein_presets_pass_their_expected_schedules(self):
        settings = {**self.manager.model_settings(), 'profile': 'klein', 'sd_profile': 'klein-3'}
        for role, name in MODEL_DEFAULTS['klein'].items():
            path = self.model_dir / name
            path.touch()
            settings[role] = str(path)
        configured = self.manager.configure(settings, persist=True)
        self.assertEqual(configured['profile'], 'klein')
        self.assertEqual(self.manager.store.load()['sd_profile'], 'klein-3')
        self.manager.start('Retrato na oficina')
        self.assertEqual(self.wait_job()['state'], 'done')
        args = json.loads(self.executable.with_suffix('.args').read_text())
        self.assertEqual(args[args.index('--steps') + 1], '3')
        actual = [float(v) for v in args[args.index('--sigmas') + 1].split(',')]
        self.assertEqual(len(actual), 4)
        for value, expected in zip(actual, (1.0, .89252933, .73462751, 0.0)):
            self.assertAlmostEqual(value, expected, places=7)

        portrait = generation_profile(SD_DEFAULTS['klein-3'], 'klein', sd_profile='klein-3',
                                      base_size=(576, 768))
        actual = [float(v) for v in portrait['schedule'][1].split(',')]
        for value, expected in zip(actual, (1.0, .889965177, .729438007, 0.0)):
            self.assertAlmostEqual(value, expected, places=7)

        self.manager.configure({**settings, 'sd_profile': 'klein'})
        self.manager.start('Retrato na oficina')
        self.assertEqual(self.wait_job()['state'], 'done')
        args = json.loads(self.executable.with_suffix('.args').read_text())
        self.assertEqual(args[args.index('--steps') + 1], '4')
        self.assertNotIn('--sigmas', args)

    def test_cli_progress_ignores_progress_bars_outside_sampling(self):
        state = {'id': 'cli-progress'}
        log = self.manager.logs / 'cli-progress.log'
        log.write_text('1/2 - 3.00s/it\n')
        self.assertIsNone(self.manager._cli_progress(state))

        with log.open('a') as stream:
            stream.write('[I] generating image: 1/1 - seed 42\n1/4 - 2.00s/it\n')
        self.assertEqual(self.manager._cli_progress(state)['total'], 4)

        with log.open('a') as stream:
            stream.write('[I] sampling completed, taking 8.00s\n1/2 - 1.00s/it\n')
        self.assertEqual(self.manager._cli_progress(state)['stage'], 'vae_decode')

    def test_qwen_cli_progress_when_persistence_is_disabled(self):
        # Only jobs explicitly configured without persistence use the CLI
        # progress parser; resident Qwen jobs use the native engine progress.
        identity='a'*32
        self.manager.job={'id':identity,'state':'running','phase':'generating',
                          'started':time.time(),
                          'settings':{'profile':'qwen-image21-experimental',
                                      'keep_loaded':False,'sd':{'steps':8}}}
        log=self.manager.logs/(identity+'.log')
        log.write_text('[I] loading llm from a.gguf\n')
        self.assertEqual(self.manager.status()['progress']['stage'],'loading_model')
        with log.open('a') as stream:
            stream.write('[I] generate_image 768x448\n\r  |===== 1/10 - 2.00s/it')
        self.assertEqual(self.manager.status()['progress']['stage'],'conditioning')
        with log.open('a') as stream:
            stream.write('\n[I] generating image: 1/1 - seed 42\n'
                         '\r |===== 1/8 - 32.33s/it - ETA 03:46'
                         '\r |========= 2/8 - 13.48s/it - ETA 01:21')
        progress=self.manager.status()['progress']
        self.assertEqual((progress['completed'],progress['total']),(2,8))
        self.assertAlmostEqual(progress['remaining_seconds'],13.48*6,delta=3)
        with log.open('a') as stream:
            stream.write('\n[I] sampling completed, taking 127.5s\n'
                         '\r |==== 1/128 - 5.0s/it')
        self.assertEqual(self.manager.status()['progress']['stage'],'vae_decode')
        # Resident jobs for either Qwen or Klein use the native progress.
        self.manager.job['settings']['keep_loaded']=True
        with patch.object(self.manager,'_cli_progress') as parse_cli:
            self.manager.status()
            parse_cli.assert_not_called()
            self.manager.job['settings']['profile']='klein'
            self.manager.status()
            parse_cli.assert_not_called()

    def test_qwen_resident_request_uses_structured_lora_and_same_sampling(self):
        import base64
        from resident import ResidentEngine
        engine=ResidentEngine()
        engine.log=self.root/'resident-request.log'
        engine.log.write_text('')
        source=self.root/'resident-reference.png'
        source.write_bytes(reference_png())
        output=self.root/'resident-output.png'
        response=[{'id':'qwen-job'}, {'status':'completed',
                  'result':{'images':[{'b64_json':base64.b64encode(reference_png()).decode()}]}}]
        profile=generation_profile(SD_DEFAULTS['qwen-image21-4'],
                                   'qwen-image21-experimental',sd_profile='qwen-image21-4',
                                   base_size=(768,448))
        with patch.object(engine,'request',side_effect=response) as request:
            engine.generate('A garden',20261122,profile,[source],output,lambda:None,
                            width=768,height=448,
                            lora=self.model_dir/'chatrlabs-omni-turbo-8step-fp32.safetensors')
        self.assertEqual(output.read_bytes(),reference_png())
        url,body=request.call_args_list[0].args[:2]
        self.assertEqual(url,'/sdcpp/v1/img_gen')
        self.assertEqual(body['prompt'],'A garden')
        self.assertEqual(body['lora'],[{'path':'chatrlabs-omni-turbo-8step-fp32.safetensors',
                                        'multiplier':1.0}])
        self.assertEqual((body['width'],body['height'],body['seed']),(768,448,20261122))
        self.assertEqual(body['sample_params']['sample_steps'],4)
        self.assertEqual(body['sample_params']['scheduler'],'simple')
        self.assertEqual(body['sample_params']['guidance']['txt_cfg'],1.0)
        self.assertEqual(body['ref_images'],[base64.b64encode(source.read_bytes()).decode()])

    def test_native_cancel_waits_for_terminal_status_and_keeps_engine(self):
        from resident import ResidentEngine
        engine=ResidentEngine()
        engine.log=self.root/'native-cancel.log'
        engine.log.touch()
        profile=generation_profile(SD_DEFAULTS['default'],'z-image-turbo',sd_profile='default',base_size=(768,448))
        output=self.root/'canceled.png'
        for success in (True,False):
            checks=iter((None,RuntimeError('Generation canceled.')))
            def check():
                result=next(checks)
                if result:raise result
            responses=[{'id':'job-1'},{'status':'generating','cancel_requested':True},
                       {'status':'cancelled'} if success else {'status':'failed'}]
            with patch.object(engine,'request',side_effect=responses) as request, patch.object(engine,'stop') as stop:
                with self.assertRaisesRegex(RuntimeError,'Generation canceled'):
                    engine.generate('A cat',1,profile,[],output,check,preserve_on_cancel=lambda:True)
                self.assertEqual(request.call_args_list[1].args,('/sdcpp/v1/jobs/job-1/cancel',{}))
                self.assertEqual(request.call_args_list[2].args,('/sdcpp/v1/jobs/job-1',))
                self.assertEqual(stop.call_count,0 if success else 1)
            self.assertFalse(output.exists())

    def test_cancel_preserves_preloaded_engine_but_close_releases_it(self):
        for preload in (True,False):
            self.manager.preload_model=preload
            self.manager.cancel_event.clear()
            with patch.object(self.manager.resident,'loaded',return_value=True), patch.object(self.manager.resident,'stop') as stop:
                self.manager.cancel()
                self.assertEqual(stop.call_count,0 if preload else 1)
        self.manager.preload_model=True
        with patch.object(self.manager.resident,'loaded',return_value=True),patch.object(self.manager.resident,'stop') as stop:
            self.manager.close()
            stop.assert_called_once()

    def test_cancel_real_worker_preserves_preloaded_resident(self):
        self.manager.preload_model=True
        self.manager.keep_loaded=True
        self.manager.executable.with_name('sd-server').touch()
        entered=threading.Event()
        def fake_generate(*args,**kwargs):
            check=args[5]
            entered.set()
            self.assertTrue(self.manager.cancel_event.wait(3))
            self.assertTrue(kwargs['preserve_on_cancel']())
            check()
        with patch.object(self.manager.resident,'ensure'),patch.object(self.manager.resident,'loaded',return_value=True),patch.object(self.manager.resident,'generate',side_effect=fake_generate),patch.object(self.manager.resident,'stop') as stop:
            self.manager.start('A cat')
            self.assertTrue(entered.wait(3))
            state=self.manager.cancel()
            self.assertEqual(state['state'],'cancelled')
            self.assertTrue(state['model_loaded'])
            stop.assert_not_called()
            self.assertFalse(self.manager.worker.is_alive())

    def test_failed_generation_does_not_start_upscaler(self):
        self.manager.start('fail')
        self.assertEqual(self.wait_job()['state'], 'error')
        self.assertFalse(self.executable.with_suffix('.upscale-args').exists())

    def test_upscale_failure_and_wrong_dimensions_are_not_success(self):
        for prompt in ('fail_upscale', 'unscaled_upscale'):
            self.manager.start(prompt)
            state = self.wait_job()
            self.assertEqual(state['state'], 'error')
            self.assertIsNone(state['image'])
            self.assertTrue((self.manager.workspace/'jobs'/state['id']/'base.png').exists())

    def test_upscale_phase_remains_busy_and_close_stops_it(self):
        self.manager.start('slow_upscale')
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.manager.status().get('phase') == 'upscaling' and self.executable.with_suffix('.upscale-args').exists():
                break
            time.sleep(0.02)
        self.assertEqual(self.manager.status().get('phase'), 'upscaling')
        with self.assertRaises(RuntimeError):
            self.manager.start('second')
        self.manager.close()
        self.assertEqual(self.manager.status()['state'], 'cancelled')

    def test_only_one_generation_runs_at_a_time(self):
        self.manager.start('slow')
        with self.assertRaises(RuntimeError):
            self.manager.start('second')
        self.assertEqual(self.wait_job()['state'], 'done')

    def test_reports_failed_process_or_invalid_output(self):
        for prompt in ('fail', 'missing', 'invalid'):
            self.manager.start(prompt)
            state = self.wait_job()
            self.assertEqual(state['state'], 'error')
            self.assertTrue(state['error'])
            self.assertIsNone(state['image'])

    def test_reports_vulkan_device_loss_and_allows_new_request(self):
        self.manager.start('device_lost')
        state = self.wait_job()
        self.assertEqual(state['state'], 'error')
        self.assertIn('lost its Vulkan context', state['error'])
        self.assertIn('logs/', state['error'])
        self.assertIsNone(state['image'])
        self.manager.start('landscape')
        self.assertEqual(self.wait_job()['state'], 'done')

    def test_missing_backend_is_reported_before_job(self):
        self.executable.unlink()
        with self.assertRaises(FileNotFoundError):
            self.manager.start('landscape')

    def test_missing_model_is_reported_before_job(self):
        self.model.unlink()
        with self.assertRaises(FileNotFoundError):
            self.manager.start('landscape')

    def test_missing_encoder_or_vae_is_reported_before_job(self):
        for component in (self.encoder, self.vae):
            component.unlink()
            with self.assertRaisesRegex(FileNotFoundError, component.name):
                self.manager.start('landscape')
            self.assertEqual(self.manager.status()['state'], 'idle')
            component.touch()

    def test_missing_upscaler_is_reported_before_job(self):
        self.upscaler.unlink()
        with self.assertRaisesRegex(FileNotFoundError, self.upscaler.name):
            self.manager.start('landscape')
        self.assertEqual(self.manager.status()['state'], 'idle')

    def test_zimage_rejects_editing_and_next_text_request_still_works(self):
        saved = self.manager.store_reference(reference_png())
        with self.assertRaisesRegex(ValueError, 'only supports text-to-image'):
            self.manager.start('change the sky', saved['id'])
        self.manager.start('new landscape')
        self.assertEqual(self.wait_job()['state'], 'done')
        self.assertNotIn('-r', json.loads(self.executable.with_suffix('.args').read_text()))

    def test_invalid_and_missing_references_are_rejected_before_job(self):
        for reference in ('../../server.py', 'f'*32, 123, ''):
            with self.assertRaises(ValueError):
                self.manager.start('edit image', reference)
            self.assertEqual(self.manager.status()['state'], 'idle')

    def test_invalid_reference_image_is_rejected(self):
        valid = reference_png()
        for data in (b'not an image', valid[:-12], valid[:25]+b'x'+valid[26:], valid+b'extra'):
            with self.assertRaises(ValueError):
                self.manager.store_reference(data)

    def test_malformed_profile_and_library_family_return_http_400(self):
        self.manager.configure(self.manager.model_settings(), persist=True)
        previous = self.manager.model_settings()
        saved = self.manager.store.path.read_bytes()
        library = self.manager.library.snapshot()
        server = create_server(self.manager, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            for path, body in [
                *[('/api/settings', {**previous, 'profile': value})
                  for value in ([], {}, None, True, 123, 'unknown')],
                *[('/api/library', {'action': 'remove', 'family': value})
                  for value in ([], {}, None, True, 123, 'unknown')],
            ]:
                with self.subTest(path=path, body=body):
                    request = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                                     headers={'Content-Type':'application/json'})
                    with self.assertRaises(urllib.error.HTTPError) as result:
                        urllib.request.urlopen(request, timeout=3)
                    with result.exception as response:
                        self.assertEqual(response.code, 400)
                        self.assertIsInstance(json.load(response)['error'], str)
            self.assertEqual(self.manager.model_settings(), previous)
            self.assertEqual(self.manager.store.path.read_bytes(), saved)
            self.assertEqual(self.manager.library.snapshot(), library)
            with urllib.request.urlopen(base + '/api/status', timeout=3) as response:
                self.assertEqual(json.load(response)['state'], 'idle')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_reference_with_valid_crc_but_invalid_pixels_is_rejected(self):
        def chunk(kind, data):
            return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
        def png(pixels):
            return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',8,8,8,2,0,0,0))
                    +chunk(b'IDAT',pixels)+chunk(b'IEND',b''))
        server = create_server(self.manager, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            for data in (png(b'invalid compressed payload'),
                         png(zlib.compress(b'\0'+b'\x20\x40\x60'*8)),
                         png(zlib.compress((b'\xff'+b'\x20\x40\x60'*8)*8))):
                request = urllib.request.Request(base + '/api/reference', data=data,
                                                 headers={'Content-Type':'image/png'})
                with self.assertRaises(urllib.error.HTTPError) as result:
                    urllib.request.urlopen(request, timeout=3)
                with result.exception as response:
                    self.assertEqual(response.code, 400)
                    self.assertIsInstance(json.load(response)['error'], str)
            self.assertEqual(list(self.manager.references.glob('*.png')), [])
            valid = reference_png()
            request = urllib.request.Request(base + '/api/reference', data=valid,
                                             headers={'Content-Type':'image/png'})
            with urllib.request.urlopen(request, timeout=3) as response:
                self.assertEqual(response.status, 201)
                saved = json.load(response)
            with urllib.request.urlopen(base + saved['image'], timeout=3) as response:
                self.assertEqual(response.read(), valid)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_reference_validation_accepts_valid_png_variants(self):
        from io import BytesIO
        from PIL import Image
        for mode in ('1', 'L', 'P', 'LA', 'RGB', 'RGBA', 'I;16'):
            with self.subTest(mode=mode):
                output = BytesIO()
                Image.new(mode, (257, 257)).save(output, format='PNG')
                data = output.getvalue()
                saved = self.manager.store_reference(data)
                self.assertEqual(self.manager.asset_bytes(saved['id'], reference=True), data)
        # Adam7: encode each of the seven passes and split IDAT across chunks.
        def chunk(kind, data):
            return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
        w,h = 19,13
        raw = bytearray()
        for x,y,dx,dy in ((0,0,8,8),(4,0,8,8),(0,4,4,8),(2,0,4,4),
                          (0,2,2,4),(1,0,2,2),(0,1,1,2)):
            for _ in range(y,h,dy):
                raw.extend(b'\0'+b'\x20\x40\x60'*len(range(x,w,dx)))
        compressed = zlib.compress(raw)
        data = (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,1))
                +chunk(b'IDAT',compressed[:7])+chunk(b'IDAT',compressed[7:])+chunk(b'IEND',b''))
        saved = self.manager.store_reference(data)
        self.assertEqual(self.manager.asset_bytes(saved['id'], reference=True), data)

    def test_obsolete_corrupt_history_is_ignored_at_startup(self):
        legacy = self.root/'jobs'
        legacy.mkdir()
        (legacy/'latest.json').write_text('[]')
        (legacy/('1'*32+'.json')).write_text('[]')
        manager = GenerationManager(self.executable,self.model_dir,
                                    upscale_model=self.upscaler,
                                    store=SettingsStore(self.root),keep_loaded=False)
        try:
            self.assertEqual(manager.status()['state'], 'idle')
            self.assertFalse(hasattr(manager, 'jobs'))
            self.assertEqual((legacy/'latest.json').read_text(), '[]')
        finally:
            manager.close()

    def test_session_files_are_removed_and_settings_survive_restart(self):
        manager = self.manager
        manager.configure(manager.model_settings(), persist=True)
        manager.library.configure(str(self.model_dir),'destination')
        saved_config = manager.store.path.read_bytes()
        saved_library = manager.library.path.read_bytes()
        workspace = manager.workspace
        identity = '2'*32
        manager.job = {'id':identity,'state':'done','image':'/images/'+identity+'.png','error':None}
        manager.last_preview_id = identity
        for name in ('resident.log','prompt-enhancer.log',identity+'.log'):
            (manager.logs/name).write_text('session diagnostics')
        reference = manager.store_reference(reference_png())
        image = manager.image_path(identity)
        image.parent.mkdir(parents=True)
        image.write_bytes(reference_png())
        self.assertTrue(manager.asset_bytes(identity))
        self.assertTrue(manager.asset_bytes(reference['id'],reference=True))
        self.assertEqual(list(workspace.rglob('*.json')), [])
        manager.close()
        self.assertFalse(workspace.exists())
        self.assertEqual(manager.store.path.read_bytes(), saved_config)
        self.assertEqual(manager.library.path.read_bytes(), saved_library)
        for name in ('logs','jobs','references','outputs'):
            self.assertFalse((self.root/name).exists())
        replacement = GenerationManager(self.executable,self.model_dir,
                                        upscale_model=self.upscaler,
                                        store=SettingsStore(self.root),keep_loaded=False)
        try:
            self.assertNotEqual(replacement.workspace, workspace)
            self.assertEqual(replacement.status()['state'],'idle')
            self.assertIsNone(replacement.asset_bytes(identity))
            self.assertIsNone(replacement.asset_bytes(reference['id'],reference=True))
            self.assertEqual(replacement.library.snapshot()['destination'],str(self.model_dir))
        finally:
            replacement.close()
        self.assertFalse(replacement.workspace.exists())

    def test_replacing_generated_result_keeps_only_latest_image(self):
        self.manager.start('first')
        first = self.wait_job()
        self.assertEqual(first['state'], 'done')
        self.assertTrue(self.manager.image_path(first['id']).is_file())
        self.manager.start('second')
        second = self.wait_job()
        self.assertEqual(second['state'], 'done')
        self.assertIsNone(self.manager.asset_bytes(first['id']))
        self.assertEqual(list((self.manager.workspace/'jobs').rglob('*.png')),
                         [self.manager.image_path(second['id'])])
        self.assertEqual(list(self.manager.workspace.rglob('*.json')), [])

    def test_new_discards_only_current_result_without_history(self):
        manager = self.manager
        current,previous = '2'*32,'3'*32
        for identity in (current,previous):
            path = manager.image_path(identity)
            path.parent.mkdir(parents=True)
            path.write_bytes(reference_png())
        manager.job = {'id':current,'state':'done','image':'/images/'+current+'.png','error':None}
        manager.last_preview_id = current
        reference = manager.store_reference(reference_png())
        server = create_server(manager, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def discard(identity):
            req = urllib.request.Request(base+'/api/jobs/'+identity+'/discard',data=b'',method='POST')
            with urllib.request.urlopen(req,timeout=3) as res:
                return json.load(res)
        try:
            self.assertFalse(discard(previous)['discarded'])
            self.assertTrue(manager.asset_bytes(current))
            manager.job['state'] = 'running'
            with self.assertRaises(urllib.error.HTTPError) as err:
                discard(current)
            self.assertEqual(err.exception.code,409)
            err.exception.close()
            manager.job['state'] = 'done'
            self.assertTrue(discard(current)['discarded'])
            self.assertEqual(manager.status()['state'],'idle')
            self.assertIsNone(manager.asset_bytes(current))
            self.assertIsNone(manager.asset_bytes(previous))
            self.assertEqual(manager.asset_bytes(reference['id'],reference=True),reference_png())
            self.assertEqual(list(manager.workspace.rglob('*.json')),[])
            self.assertFalse(discard(current)['discarded'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_persistent_child_survives_request_thread_and_stops_with_guard(self):
        from processes import spawn
        from resident import terminate
        ready, release = threading.Event(), threading.Event()
        processes = []
        def request_thread():
            process = spawn([sys.executable,'-u','-c',
                             'import os,time; print(os.getpid(),flush=True); time.sleep(20)'],
                            stdout=subprocess.PIPE,text=True)
            processes.append(process)
            process.native_pid = int(process.stdout.readline())
            ready.set()
            release.wait(5)
        worker = threading.Thread(target=request_thread)
        worker.start()
        try:
            self.assertTrue(ready.wait(5),'child did not reach exec')
            release.set()
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            time.sleep(.1)
            self.assertIsNone(processes[0].poll(),'engine stopped when request thread exited')
            terminate(processes[0])
            self.assertIsNotNone(processes[0].poll())
            native_status=Path(f'/proc/{processes[0].native_pid}/status')
            self.assertTrue(not native_status.exists() or '\nState:\tZ' in native_status.read_text())
        finally:
            release.set()
            worker.join(timeout=5)
            for process in processes:
                terminate(process)
                process.stdout.close()

    def test_server_signals_stop_backend(self):
        binary = self.executable
        for stop_signal in (signal.SIGTERM, signal.SIGINT):
            backend_pid = None
            pidfile = binary.with_suffix('.pid')
            pidfile.unlink(missing_ok=True)
            bootstrap = """import server,sys
from pathlib import Path
server.ROOT=Path(sys.argv[1])
server.NCNN_EXECUTABLE=Path(sys.argv[2])
server.hardware.discover=lambda _: [dict(index=0,name='Test',type=2,total=8*1024**3,free=7*1024**3,usable=True,ggml='Vulkan0')]
server.model_catalog.validate=lambda *args:None
binary=Path(sys.argv[2])
original=server.GenerationManager.__init__
def init(self, executable, *a, **kw):
    original(self,binary,*a,keep_loaded=False,**kw)
    (server.ROOT/'test-workspace.txt').write_text(str(self.workspace))
server.GenerationManager.__init__=init
sys.argv=['server.py','--port','0','--model-dir',sys.argv[3],'--upscale-model',sys.argv[4]]
server.main()
"""
            process = subprocess.Popen([sys.executable,'-c',bootstrap,str(self.root),str(binary),str(self.model_dir),str(self.upscaler)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)

            try:
                line = process.stdout.readline()
                if not line: self.fail(process.stderr.read())
                base = line.split()[1]
                request = urllib.request.Request(base + '/api/generate', data=b'{"prompt":"block"}', headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request):
                    pass
                deadline = time.monotonic() + 3
                while not pidfile.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(pidfile.exists())
                backend_pid = int(pidfile.read_text())
                process.send_signal(stop_signal)
                process.wait(timeout=5)
                workspace = Path((self.root/'test-workspace.txt').read_text())
                self.assertFalse(workspace.exists(), 'session files survived server shutdown')
                proc_status = Path(f'/proc/{backend_pid}/status')
                self.assertTrue(not proc_status.exists() or '\nState:\tZ' in proc_status.read_text(), 'backend still running after server stopped')
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)
                if backend_pid:
                    try:
                        os.kill(backend_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_http_generation_and_path_restrictions(self):
        server = create_server(self.manager, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(base + '/pose.html') as response:
                self.assertIn("frame-ancestors 'self'",response.headers['Content-Security-Policy'])
                self.assertIn(b'/pose.js',response.read())
            for path in ('/pose.js','/pose.css'):
                with urllib.request.urlopen(base + path) as response:
                    self.assertEqual(response.status,200)
                    self.assertNotIn("'unsafe-inline'",response.headers['Content-Security-Policy'])
            with urllib.request.urlopen(base + '/eyes.js?v=mascot1') as response:
                self.assertIn('text/javascript', response.headers['Content-Type'])
                self.assertIn(b'scheduleBlink', response.read())
            request = urllib.request.Request(base + '/api/reference', data=reference_png(), headers={'Content-Type':'image/png'})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 201)
                saved = json.load(response)
            with urllib.request.urlopen(base + saved['image']) as response:
                self.assertEqual(response.read(), reference_png())
            request = urllib.request.Request(base + '/api/generate', data=json.dumps({'prompt':'landscape', 'seed': 7041}).encode(), headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 202)
                self.assertEqual(json.load(response)['seed'], 7041)
            state = self.wait_job()
            with urllib.request.urlopen(base + state['image']) as response:
                self.assertEqual(response.headers['Content-Type'], 'image/png')
            for path in ('/images/../../server.py', '/images/unknown.png', '/server.py'):
                with self.assertRaises(urllib.error.HTTPError) as result:
                    urllib.request.urlopen(base + path)
                self.assertEqual(result.exception.code, 404)
                result.exception.close()
            request = urllib.request.Request(base + '/api/generate', data=b'{"prompt":"test"}', headers={'Content-Type':'application/json', 'Origin':'https://example.com'})
            with self.assertRaises(urllib.error.HTTPError) as result:
                urllib.request.urlopen(request)
            self.assertEqual(result.exception.code, 403)
            result.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
