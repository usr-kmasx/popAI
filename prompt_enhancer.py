"""Owned CPU-only llama-server, preloaded once and streamed through the app."""
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
CONTEXT_SIZE = 2048


class PromptEnhancer:
    def __init__(self, logs, root=APP_ROOT, port=8081):
        self.root=Path(root)
        self.logs=Path(logs)
        self.port=port
        self.binary=self.root/'backends/llama-cpu/llama-server'
        self.model=self.root/'models/prompt-enhancer/LFM3-1.7B-Uncensored-AD-Q4_K_M.gguf'
        self.system=(RESOURCE_ROOT/'prompt-enhancer-system.txt').read_text(encoding='utf-8')
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

    def status(self):
        with self.lock:
            if self.state=='ready' and self.process and self.process.poll() is not None:
                self.state='error';self.error='O melhorador foi encerrado. Clique em melhorar para tentar novamente.'
            return {'state':self.state,'error':self.error,'busy':self.busy}

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
            # Only retire our previous failed child; never adopt a foreign port.
            terminate(self.process)
            with self.lock:self.process=None
            if not self.binary.is_file() or not self.model.is_file():
                raise RuntimeError('Melhorador ausente. Execute tools/setup-prompt-enhancer.py no projeto.')
            # Never attach to, replace or stop a server owned by another app.
            with socket.socket() as listener:
                listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                try:listener.bind(('127.0.0.1',self.port))
                except OSError as exc:raise RuntimeError(f'A porta {self.port} do melhorador já está ocupada.') from exc
            command=[str(self.binary),'-m',str(self.model),'-ngl','0','--device','none',
                     '-c',str(CONTEXT_SIZE),'--parallel','1','--reasoning','off','--no-context-shift',
                     '--host','127.0.0.1','--port',str(self.port),'--threads',str(min(4,os.cpu_count() or 1))]
            self.logs.mkdir(parents=True,exist_ok=True)
            env=dict(os.environ,LLAMA_API_KEY=self.token)
            # No inherited preload/offload options can select an external model.
            for key in list(env):
                if key.startswith(('LLAMA_ARG_','LLAMA_OFFLINE','LLAMA_MODEL_')):env.pop(key,None)
            with self.lock:
                if self.stop_event.is_set():return
                with (self.logs/'prompt-enhancer.log').open('a',encoding='utf-8') as output:
                    self.process=spawn(command,cwd=self.root,env=env,stdout=output,stderr=subprocess.STDOUT)
                process=self.process
            deadline=time.monotonic()+120
            while not self.stop_event.wait(.2):
                if process.poll() is not None:raise RuntimeError('O melhorador não carregou. Consulte logs/prompt-enhancer.log.')
                if time.monotonic()>deadline:raise RuntimeError('O carregamento do melhorador excedeu o tempo permitido.')
                try:
                    req=Request(self.url+'/health',headers={'Authorization':'Bearer '+self.token})
                    with self.http.open(req,timeout=1) as response:ready=json.load(response).get('status')=='ok'
                    if ready:
                        req=Request(self.url+'/v1/models',headers={'Authorization':'Bearer '+self.token})
                        with self.http.open(req,timeout=1) as response:json.load(response)
                        with self.lock:
                            if not self.stop_event.is_set():self.state='ready'
                        return
                except (OSError,ValueError):pass
        except Exception as exc:
            with self.lock:self.state='error';self.error=str(exc)
            terminate(self.process)

    def stream(self,prompt,editing=False):
        if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>MAX_PROMPT_CHARS or '\0' in prompt:
            raise ValueError('Escreva uma descrição válida antes de melhorar.')
        if not isinstance(editing,bool):raise ValueError('Tipo de pedido inválido.')
        if not self.request_lock.acquire(blocking=False):raise RuntimeError('Já existe um prompt sendo melhorado.')
        try:
            with self.lock:
                self.request_cancel.clear()
                self.busy=True
            if self.stop_event.is_set():raise RuntimeError('O melhorador está encerrando.')
            yield {'state':'started'}
            if self.status()['state']!='ready':
                self.start()
                deadline=time.monotonic()+120
                while True:
                    if self.stop_event.is_set() or self.request_cancel.is_set():raise RuntimeError('Melhoria cancelada.')
                    state=self.status()
                    if state['state']=='ready':break
                    if state['state']=='error':raise RuntimeError(state['error'])
                    if time.monotonic()>deadline:raise RuntimeError('O melhorador ainda está carregando. Tente novamente.')
                    self.request_cancel.wait(.1)
            instruction = ('Rewrite this image edit as an English instruction:' if editing else
                           'Rewrite this image description as an English prompt:')
            messages = [
                {'role': 'system', 'content': self.system},
                {'role': 'user', 'content': f'{instruction}\n\n{prompt.strip()}'},
            ]
            body={'messages':messages,
                  'stream':True,'max_tokens':-1,'temperature':.4,'top_p':.9,'cache_prompt':True}
            complete=False;written=0;finish=None;started=time.monotonic()
            connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=120)
            try:
                connection.request('POST','/v1/chat/completions',body=json.dumps(body).encode('utf-8'),
                                   headers={'Content-Type':'application/json','Authorization':'Bearer '+self.token})
                with self.lock:self.native_socket=connection.sock
                if self.request_cancel.is_set():raise RuntimeError('Melhoria cancelada.')
                response=connection.getresponse()
                if response.status!=200:
                    detail=response.read(8192).decode('utf-8',errors='replace')
                    try:detail=json.loads(detail).get('error',{}).get('message',detail)
                    except (ValueError,AttributeError):pass
                    raise RuntimeError(f'O melhorador recusou o pedido: {detail}')
                for raw in response:
                    if self.stop_event.is_set() or self.request_cancel.is_set():raise RuntimeError('Melhoria cancelada.')
                    if time.monotonic()-started>120:raise RuntimeError('A melhoria excedeu o tempo permitido.')
                    line=raw.decode('utf-8').strip()
                    if not line.startswith('data:'):continue
                    data=line[5:].strip()
                    if data=='[DONE]':complete=True;break
                    event=json.loads(data)
                    if event.get('error'):raise RuntimeError(str(event['error']))
                    for choice in event.get('choices',[]):
                        finish=choice.get('finish_reason') or finish
                        token=choice.get('delta',{}).get('content') or ''
                        if token:
                            written+=len(token)
                            if written>MAX_PROMPT_CHARS:raise RuntimeError('O resultado excedeu o tamanho do campo. Tente uma descrição mais curta.')
                            yield {'text':token}
            finally:
                connection.close()
                with self.lock:self.native_socket=None
            if not complete or not written:raise RuntimeError('O melhorador não concluiu o texto. Tente novamente.')
            if finish=='length':raise RuntimeError(f'O contexto de {CONTEXT_SIZE} foi atingido. Tente uma descrição mais curta.')
            yield {'state':'done','seconds':round(time.monotonic()-started,2)}
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
        with self.lock:process=self.process
        terminate(process)
        if self.worker and self.worker is not threading.current_thread():self.worker.join(timeout=5)
        with self.lock:self.state='stopped'
