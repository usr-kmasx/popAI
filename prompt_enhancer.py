"""Two private completion stages in one owned Vulkan llama-server session."""
import json
import http.client
import os
import secrets
import socket
import subprocess
import threading
import time
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

from app_config import APP_ROOT, RESOURCE_ROOT
from processes import spawn
from resident import terminate

MAX_PROMPT_CHARS = 16000
CONTEXT_SIZE = 8192
REASONING_BUDGET = 1024
CORRECTOR_REASONING_BUDGET = 1024
LITE_CONTEXT_SIZE = 4096
LITE_CORRECTOR_REASONING_BUDGET = 512
LITE_REASONING_BUDGET = 192
PROMPT_PROCESSING_DEFAULTS = {'corrector': True, 'enhancer': True, 'lite': False}


def normalize_prompt_processing(options):
    if not isinstance(options, dict) or set(options) - set(PROMPT_PROCESSING_DEFAULTS):
        raise ValueError('Invalid prompt processing settings.')
    result = {**PROMPT_PROCESSING_DEFAULTS, **options}
    if any(type(value) is not bool for value in result.values()):
        raise ValueError('Prompt processing options must be boolean.')
    return result


CORRECTOR_TEMPERATURE = .1
HEARTBEAT_INTERVAL = 1.0
ENHANCER_MODES = {
    'simple': ('prompt-enhancer-system.txt', .4, ''),
    'detailed': ('prompt-enhancer-detailed.txt', .2,
                 'Add new, concrete visual details the original does not specify. Develop the main subject and any other important elements with room for detail.'),
    'creative': ('prompt-enhancer-creative.txt', .55,
                 'Give the stated scene four new visual details that fit together.'),
    'cinematic': ('prompt-enhancer-cinematic.txt', .3, ''),
}


class PromptEnhancer:
    def __init__(self, logs, root=APP_ROOT, port=8081):
        self.root=Path(root)
        self.logs=Path(logs)
        self.port=port
        self.binary=self.root/'backends/llama-vulkan/llama-server'
        model_config=json.loads((self.root/'prompt-enhancer.json').read_text(encoding='utf-8'))['model']
        self.model=self.root/model_config['directory']/model_config['filename']
        self.systems = {
            mode: (RESOURCE_ROOT / filename).read_text(encoding='utf-8')
            for mode, (filename, _, _) in ENHANCER_MODES.items()
        }
        self.options = dict(PROMPT_PROCESSING_DEFAULTS)
        self.corrector_system = (RESOURCE_ROOT / 'prompt-corrector.txt').read_text(encoding='utf-8')
        self.lock=threading.RLock()
        self.request_lock=threading.Lock()
        self.stop_event=threading.Event()
        self.process=None
        self.worker=None
        self.state='stopped'
        self.error=None
        self.busy=False
        self.request_cancel=threading.Event()
        self.native_socket=None
        self.token=secrets.token_urlsafe(32)
        self.http=build_opener(ProxyHandler({}))
        self.url=f'http://127.0.0.1:{port}'

    @property
    def context_size(self):
        return LITE_CONTEXT_SIZE if self.options['lite'] else CONTEXT_SIZE

    @property
    def corrector_budget(self):
        return LITE_CORRECTOR_REASONING_BUDGET if self.options['lite'] else CORRECTOR_REASONING_BUDGET

    @property
    def enhancer_budget(self):
        return LITE_REASONING_BUDGET if self.options['lite'] else REASONING_BUDGET

    def status(self):
        with self.lock:
            if self.state=='ready' and self.process and self.process.poll() is not None:
                self.state='error';self.error='The prompt enhancer stopped. Click Enhance to try again.'
            return {'state':self.state,'error':self.error,'busy':self.busy,'options':dict(self.options)}

    def start(self):
        with self.lock:
            if self.stop_event.is_set():return
            if self.worker and self.worker.is_alive():return
            if self.process and self.process.poll() is None and self.state=='ready':return
            self.state='loading'
            self.error=None
            self.worker=threading.Thread(target=self._load,daemon=True)
            self.worker.start()

    def _load(self):
        try:
            # A new isolated GPU process is started only for this enhancement.
            if self.stop_event.is_set() or self.request_cancel.is_set():return
            with self.lock:self.process=None
            if not self.binary.is_file() or not self.model.is_file():
                raise RuntimeError('The prompt enhancer is missing. Run ./install.sh from the project folder.')
            # Never attach to, replace or stop a server owned by another app.
            with socket.socket() as listener:
                listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                try:listener.bind(('127.0.0.1',self.port))
                except OSError as exc:raise RuntimeError(f'Prompt enhancer port {self.port} is already in use.') from exc
            command=[str(self.binary),'-m',str(self.model),'-ngl','999','--device','Vulkan0',
                     '-c',str(self.context_size),'--parallel','1',
                     '--cache-type-k','q4_0','--cache-type-v','q4_0','--flash-attn','on',
                     '--reasoning','on','--reasoning-budget',str(max(self.corrector_budget,self.enhancer_budget)),
                     '--reasoning-format','deepseek','--no-context-shift',
                     '--host','127.0.0.1','--port',str(self.port),'--threads',str(min(4,os.cpu_count() or 1))]
            self.logs.mkdir(parents=True,exist_ok=True)
            env=dict(os.environ,LLAMA_API_KEY=self.token)
            # No inherited preload/offload options can select an external model.
            for key in list(env):
                if key.startswith(('LLAMA_ARG_','LLAMA_OFFLINE','LLAMA_MODEL_')):env.pop(key,None)
            with self.lock:
                if self.stop_event.is_set() or self.request_cancel.is_set():return
                with (self.logs/'prompt-enhancer.log').open('a',encoding='utf-8') as output:
                    self.process=spawn(command,cwd=self.root,env=env,stdout=output,stderr=subprocess.STDOUT)
                process=self.process
            deadline=time.monotonic()+120
            while not self.stop_event.wait(.2):
                if self.request_cancel.is_set():return
                if process.poll() is not None:raise RuntimeError(f'The prompt enhancer failed to load. Session log: {self.logs / 'prompt-enhancer.log'}.')
                if time.monotonic()>deadline:raise RuntimeError('The prompt enhancer took too long to load.')
                try:
                    req=Request(self.url+'/health',headers={'Authorization':'Bearer '+self.token})
                    with self.http.open(req,timeout=1) as response:ready=json.load(response).get('status')=='ok'
                    if ready:
                        req=Request(self.url+'/v1/models',headers={'Authorization':'Bearer '+self.token})
                        with self.http.open(req,timeout=1) as response:json.load(response)
                        with self.lock:
                            if not self.stop_event.is_set() and not self.request_cancel.is_set():self.state='ready'
                        return
                except (OSError,ValueError):pass
        except Exception as exc:
            with self.lock:
                if not self.stop_event.is_set() and not self.request_cancel.is_set():
                    self.state='error';self.error=str(exc)
                process=self.process
                self.process=None
            terminate(process)

    def _release(self):
        # Setting cancellation under the same lock as spawning prevents late GPU loads.
        with self.lock:
            self.request_cancel.set()
            process=self.process
            self.process=None
            self.state='stopped'
            self.error=None
        if process is not None:terminate(process)
        worker=self.worker
        if worker and worker is not threading.current_thread():worker.join(timeout=5)

    def _check_cancel(self):
        if self.stop_event.is_set() or self.request_cancel.is_set():
            raise RuntimeError('Prompt enhancement canceled.')

    def _complete(self, system, user_message, temperature, *, phase, reasoning_budget=REASONING_BUDGET):
        """Stream model-emitted reasoning and answer deltas to the local popup.
        Return only a validated answer for the next stage or final prompt.
        """
        self._check_cancel()
        body = {
            'messages': [
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': user_message},
            ],
            'stream': True, 'max_tokens': -1,
            'temperature': temperature, 'top_p': .9,
            'cache_prompt': False,
            'reasoning_budget_tokens': reasoning_budget,
        }
        complete = False
        finish = None
        parts = []
        written = 0
        thought_written = 0
        started = time.monotonic()
        last_heartbeat = started
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=120)
        try:
            connection.request('POST', '/v1/chat/completions',
                               body=json.dumps(body).encode('utf-8'),
                               headers={'Content-Type': 'application/json',
                                        'Authorization': 'Bearer ' + self.token})
            with self.lock:
                self.native_socket = connection.sock
            self._check_cancel()
            response = connection.getresponse()
            if response.status != 200:
                # The native error may include the prompt or local paths; keep it private.
                raise RuntimeError('The prompt enhancer rejected a request. Try a shorter description.')
            for raw in response:
                self._check_cancel()
                now = time.monotonic()
                if now - started > 120:
                    raise RuntimeError('Prompt enhancement timed out.')
                line = raw.decode('utf-8').strip()
                if line.startswith('data:'):
                    data = line[5:].strip()
                    if data == '[DONE]':
                        complete = True
                        break
                    event = json.loads(data)
                    if event.get('error'):
                        raise RuntimeError('The prompt enhancer could not complete the request. Try again.')
                    for choice in event.get('choices', []):
                        finish = choice.get('finish_reason') or finish
                        delta = choice.get('delta', {})
                        thought = delta.get('reasoning_content')
                        if isinstance(thought, str) and thought and thought_written < MAX_PROMPT_CHARS:
                            thought = thought[:MAX_PROMPT_CHARS - thought_written]
                            thought_written += len(thought)
                            yield {'phase': phase, 'thought': thought}
                            self._check_cancel()
                        token = delta.get('content') or ''
                        if token:
                            written += len(token)
                            if written > MAX_PROMPT_CHARS:
                                raise RuntimeError('The enhanced prompt exceeded the character limit. Try a shorter description.')
                            parts.append(token)
                            yield {'phase': phase, 'answer': token}
                            self._check_cancel()
                if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                    last_heartbeat = now
                    yield {'state': 'working'}
        except OSError as exc:
            self._check_cancel()
            raise RuntimeError('The prompt enhancer connection was interrupted. Try again.') from exc
        finally:
            connection.close()
            with self.lock:
                self.native_socket = None
        self._check_cancel()
        if finish == 'length':
            raise RuntimeError(f'The prompt enhancer reached its {self.context_size}-token context limit. Try a shorter description.')
        result = ''.join(parts).strip()
        if not complete or finish != 'stop' or not result:
            raise RuntimeError('The prompt enhancer did not finish. Try again.')
        return result

    def stream(self,prompt,editing=False,*,mode='simple'):
        if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>MAX_PROMPT_CHARS or '\0' in prompt:
            raise ValueError('Enter a valid description before enhancing the prompt.')
        if not isinstance(editing,bool):raise ValueError('Invalid request type.')
        if not isinstance(mode, str) or mode not in (*ENHANCER_MODES, 'corrector'):
            raise ValueError('Choose Simple, More details, Creative, or Dramatic.')
        if not self.request_lock.acquire(blocking=False):raise RuntimeError('A prompt is already being enhanced.')
        try:
            with self.lock:
                self.request_cancel.clear()
                self.busy=True
            if self.stop_event.is_set():raise RuntimeError('The prompt enhancer is shutting down.')
            options = dict(self.options)
            if not (options['corrector'] or options['enhancer']):
                raise ValueError('Enable Corrector or Enhancer in Settings first.')
            if not options['enhancer'] and mode != 'corrector':
                raise ValueError('Enhancer is disabled. Use Correct prompt instead.')
            if mode == 'corrector' and (not options['corrector'] or options['enhancer']):
                raise ValueError('Correct prompt is only available when Corrector alone is enabled.')
            yield {'state':'started'}
            if self.status()['state']!='ready':
                self.start()
                deadline=time.monotonic()+120
                last_heartbeat=time.monotonic()
                while True:
                    self._check_cancel()
                    state=self.status()
                    if state['state']=='ready':break
                    if state['state']=='error':raise RuntimeError(state['error'])
                    now=time.monotonic()
                    if now>deadline:raise RuntimeError('The prompt enhancer is still loading. Try again.')
                    if now-last_heartbeat>=HEARTBEAT_INTERVAL:
                        last_heartbeat=now
                        yield {'state':'working'}
                    self.request_cancel.wait(.1)
            self._check_cancel()
            started=time.monotonic()
            corrected = prompt.strip()
            if options['corrector']:
                # Stage 1 (optional): the corrector
                # resolves its meaning and returns a plain en-US paragraph.
                correction_instruction = (
                    'Interpret, correct, and translate this reference-image edit into en-US:'
                    if editing else
                    'Interpret, correct, and translate this image description into en-US:'
                )
                yield {'stage': 'corrector'}
                corrected = yield from self._complete(
                    self.corrector_system,
                    f'{correction_instruction}\n\n{prompt.strip()}',
                    CORRECTOR_TEMPERATURE,
                    phase='corrector', reasoning_budget=self.corrector_budget,
                )
            enhanced = corrected
            if options['enhancer']:
                # Same loaded model, new independent request. Only the corrected
                # paragraph (or original input when disabled) is passed to the mode; no history.
                self._check_cancel()
                yield {'state':'working'}
                self._check_cancel()
                instruction = ('Rewrite this image edit as an English instruction:' if editing else
                               'Rewrite this image description as an English prompt:')
                _, temperature, mode_instruction = ENHANCER_MODES[mode]
                user_message = f'{instruction}\n\n{corrected}'
                if mode_instruction:
                    if editing:
                        mode_instruction += ' Enrich only the requested change. Preserving the scope of the edit takes priority over adding detail.'
                        opening = 'Start directly with the requested change.'
                    else:
                        opening = 'Start directly with the main subject.'
                    user_message += (f'\n\n{mode_instruction} Show the same subjects, actions, and place in the same moment. '
                                     f'Write only the finished English paragraph. {opening}')
                yield {'stage': 'enhancer'}
                enhanced = yield from self._complete(self.systems[mode], user_message, temperature, phase='enhancer', reasoning_budget=self.enhancer_budget)
            self._check_cancel()
            # Release VRAM before committing the complete result to the input.
            # Stage deltas are displayed separately and never replace the input.
            self._release()
            yield {'text':enhanced}
            yield {'state':'done','seconds':round(time.monotonic()-started,2)}
        finally:
            try:self._release()
            finally:
                with self.lock:self.busy=False
                self.request_lock.release()

    def cancel_current(self):
        with self.lock:
            if self.busy:self.request_cancel.set()
            channel=self.native_socket
        if channel:
            try:channel.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        return self.status()

    def close(self):
        self.stop_event.set()
        self.cancel_current()
        self._release()
