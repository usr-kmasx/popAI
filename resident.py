"""Owned, local stable-diffusion.cpp process for reuse between requests."""
from errors import native_failure
from processes import spawn
import base64
import json
import os
import secrets
import signal
import socket
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


def terminate(process):
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=3)
    except ProcessLookupError:
        pass


class ResidentEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.process = None
        self.url = None
        self.ready = False
        self.has_vision = False
        self.signature = None
        self.log = None
        self.log_start = 0
        self.http = build_opener(ProxyHandler({}))
        self.token = secrets.token_urlsafe(32)

    def stop(self):
        with self.lock:
            process = self.process
            self.process = None
            self.ready = False
            self.has_vision = False
            self.signature = None
        terminate(process)

    def loaded(self):
        with self.lock:
            return bool(self.ready and self.process and self.process.poll() is None)

    def request(self, path, body=None, timeout=5):
        data = None if body is None else json.dumps(body).encode('utf-8')
        request = Request(self.url + path, data=data, headers={'Content-Type': 'application/json', 'X-PopAI-Token': self.token})
        try:
            with self.http.open(request, timeout=timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read()).get('error', str(exc))
            except (ValueError, OSError):
                detail = str(exc)
            if self.log:
                raise native_failure(self.log,'request processing',detail=str(detail),offset=self.log_start) from exc
            raise RuntimeError(f'The persistent engine rejected the request: {detail}') from exc

    def ensure(self, command, env, root, log, vision, check):
        self.log = log
        from pathlib import Path
        components = []
        for flag in ('--diffusion-model','--llm','--vae'):
            if flag in command:
                path = Path(command[command.index(flag)+1])
                stat = path.stat()
                components.append((str(path),stat.st_size,stat.st_mtime_ns))
        signature = (tuple(command),tuple(components),str(root),tuple((key,env.get(key)) for key in ('GGML_VK_VISIBLE_DEVICES','GGML_VK_MAX_NODES_PER_SUBMIT','GGML_VK_SERIALIZE_SUBMISSIONS','VK_DRIVER_FILES','VK_ICD_FILENAMES')))
        if self.loaded() and self.signature == signature and (not vision or self.has_vision):
            return
        self.stop()
        self.log_start = log.stat().st_size if log.exists() else 0
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        with self.lock:
            check()
            self.url = f'http://127.0.0.1:{port}'
            args = command + ['--listen-ip', '127.0.0.1', '--listen-port', str(port),
                              '--max-pending-jobs', '1', '--completed-ttl-seconds', '2']
            if vision:
                args += ['--llm_vision', str(vision)]
            with log.open('a', encoding='utf-8') as stream:
                self.process = spawn(args, cwd=root, env=dict(env, POP_AI_INTERNAL_TOKEN=self.token), stdout=stream,
                                                stderr=subprocess.STDOUT)
            process = self.process
        while True:
            check()
            if process.poll() is not None:
                raise native_failure(log,'model loading',process.returncode,offset=self.log_start)
            try:
                state = self.request('/sdcpp/v1/models/status', timeout=1)
                if state.get('state') == 'ready':
                    with self.lock:
                        if self.process is process:
                            self.ready = True
                            self.has_vision = bool(vision)
                            self.signature = signature
                            return
                if state.get('state') == 'error':
                    raise native_failure(log,'model loading',detail=str(state.get('error','')),offset=self.log_start)
            except (URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(.2)

    def generate(self, prompt, seed, profile, references, output, check, width=960, height=544, on_progress=None, preview_path=None):
        self.log_start = self.log.stat().st_size if self.log and self.log.exists() else 0
        sample = {'sample_method': profile.get('sampler', 'euler'), 'sample_steps': int(profile['steps']),
                  'guidance': {'txt_cfg': float(profile['cfg'])}}
        if profile['schedule'][:1] == ['--scheduler']:
            sample['scheduler'] = profile['schedule'][1]
        if profile['schedule'][:1] == ['--sigmas']:
            sample['custom_sigmas'] = [float(value) for value in profile['schedule'][1].split(',')]
        check()
        submitted = self.request('/sdcpp/v1/img_gen', {
            'prompt': prompt, 'width': width, 'height': height, 'seed': seed,
            'sample_params': sample, 'vae_tiling_params': {'enabled': profile.get('vae_tiling',True), **({'tile_size_w':profile['vae_tile_size'],'tile_size_h':profile['vae_tile_size']} if profile.get('vae_tile_size') else {})},
            'ref_images': [base64.b64encode(path.read_bytes()).decode('ascii') for path in references],
            'batch_count': 1, 'preview': 'proj' if preview_path else 'none',
            'preview_interval': 1, 'output_format': 'png',
        }, timeout=30)
        last_preview = None
        while True:
            check()
            state = self.request('/sdcpp/v1/jobs/' + submitted['id'])
            if on_progress:
                on_progress(state.get('progress',{}))
            preview = state.get('preview')
            if preview_path and preview:
                revision = (preview.get('pass'), preview.get('step'))
                if revision != last_preview:
                    try:
                        pixels = base64.b64decode(preview['b64_json'], validate=True)
                        preview_path.write_bytes(pixels)
                    except (KeyError, ValueError, OSError):
                        pass
                    else:
                        last_preview = revision
            if state['status'] == 'completed':
                check()
                output.write_bytes(base64.b64decode(state['result']['images'][0]['b64_json'], validate=True))
                return
            if state['status'] in {'failed', 'cancelled'}:
                raise native_failure(self.log,'image generation',detail=str(state.get('error') or state['status']),offset=self.log_start)
            time.sleep(.3)

