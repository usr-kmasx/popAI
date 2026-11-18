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
width,height = (1920,1088) if upscale and prompt != 'unscaled_upscale' else (960,544)
png = b'\\x89PNG\\r\\n\\x1a\\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
png += chunk(b'IDAT', zlib.compress((b'\\0' + bytes([16, 32, 48])*width)*height)) + chunk(b'IEND', b'')
out.write_bytes(png if prompt != 'invalid' else b'broken')
''')
        self.executable.chmod(0o755)
        self.manager = GenerationManager(self.executable, self.model_dir, self.root / 'outputs', self.root / 'logs', upscale_model=self.upscaler,store=SettingsStore(self.root))
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
        self.assertIn('contexto Vulkan', state['error'])
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
        with self.assertRaisesRegex(ValueError, 'somente por texto'):
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
    original(self,binary,*a,**kw)
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
            request = urllib.request.Request(base + '/api/reference', data=reference_png(), headers={'Content-Type':'image/png'})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 201)
                saved = json.load(response)
            with urllib.request.urlopen(base + saved['image']) as response:
                self.assertEqual(response.read(), reference_png())
            request = urllib.request.Request(base + '/api/generate', data=json.dumps({'prompt':'landscape'}).encode(), headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 202)
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
