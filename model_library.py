"""Local model library and verified, resumable downloads. No inference dependencies."""
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import ctypes
import errno
from pathlib import Path
from urllib.request import Request, urlopen

from app_config import RESOURCE_ROOT, local_path, normalize_roots
import model_catalog


# Directory names are user-facing and stable. Sampling presets share the same
# weights, so they must not create duplicate multi-gigabyte model directories.
MODEL_SET_DIRECTORIES = {
    'z-image-turbo': 'Z-Image Turbo',
    'klein': 'FLUX.2 Klein 4B',
    'qwen-image21-experimental': 'Qwen Image 2.1',
}


class Cancelled(Exception):
    pass


class ModelLibrary:
    def __init__(self, root, roots, manifest=None):
        self.path = Path(root) / 'model-library.json'
        self.manifest = manifest if manifest is not None else json.loads((RESOURCE_ROOT/'model-downloads.json').read_text())
        self.lock = threading.RLock()
        self.cancel_event = threading.Event()
        self.worker = None
        self.closed = False
        self.state = {'state':'idle'}
        self.data = {'roots':[str(p) for p in roots], 'destination':'', 'managed':{},'verified':{}}
        self.error = None
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self.data['roots'] = [str(p) for p in normalize_roots(data['roots'])]
                self.data['destination'] = str(local_path(data['destination'])) if data.get('destination') else ''
                if not isinstance(data.get('managed',{}),dict):
                    raise ValueError('Invalid file registry.')
                self.data['managed'] = data.get('managed',{})
                if not isinstance(data.get('verified',{}),dict):raise ValueError('Invalid verification record.')
                self.data['verified']=data.get('verified',{})
            except (ValueError, KeyError, TypeError, OSError) as exc:
                self.error = f'Check the saved model library. Details: {exc}'

    def _save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,name = tempfile.mkstemp(prefix='.library-',dir=self.path.parent)
        try:
            with os.fdopen(fd,'w') as output:
                json.dump(self.data,output,ensure_ascii=False,indent=2)
                output.flush(); os.fsync(output.fileno())
            os.replace(name,self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def roots(self):
        with self.lock:
            return [Path(p) for p in self.data['roots']]

    def snapshot(self):
        with self.lock:
            return {**copy.deepcopy(self.data), 'operation':copy.deepcopy(self.state),
                    'manifest':self.manifest, 'error':self.error}

    def verifications(self):
        with self.lock:records=copy.deepcopy(self.data['verified'])
        fresh={}
        for path,record in records.items():
            try:
                stat=Path(path).stat()
                if stat.st_size==record['size'] and stat.st_mtime_ns==record['mtime_ns']:fresh[path]=record
            except (OSError,KeyError,TypeError):continue
        return fresh

    def configure(self, folder, action):
        if not isinstance(folder,str) or not folder.strip() or '\0' in folder:
            raise ValueError('Choose a folder.')
        path = local_path(folder.strip())
        if action!='forget' and not path.is_dir():
            raise ValueError('Choose an existing folder.')
        with self.lock:
            self._available()
            previous=copy.deepcopy(self.data)
            try:
                roots=self.data['roots']
                if action=='forget':
                    if str(path) not in roots:
                        raise ValueError('The folder is not registered.')
                    if len(roots)==1:
                        raise ValueError('Add another folder before removing this one.')
                    roots.remove(str(path))
                    if self.data['destination']==str(path):self.data['destination']=''
                elif action in ('destination','add'):
                    if str(path) not in roots:roots.append(str(path))
                    if len(roots)>32:raise ValueError('You can add up to 32 folders.')
                    if action=='destination':
                        with tempfile.TemporaryFile(dir=path):pass
                        self.data['destination']=str(path)
                else:raise ValueError('Invalid folder action.')
                self._save()
                self.error=None
            except Exception:
                self.data=previous
                raise
        return self.snapshot()

    @staticmethod
    def folders(value=None):
        if value is not None and (not isinstance(value,str) or '\0' in value):
            raise ValueError('Invalid folder.')
        path=local_path(value) if value else Path.home()
        if not path.is_dir():raise ValueError('The folder is unavailable.')
        children=[]
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_dir() and not entry.name.startswith('.'):
                        children.append({'name':entry.name,'path':str(Path(entry.path).resolve())})
                except OSError:continue
        children.sort(key=lambda p:p['name'].casefold())
        return {'path':str(path),'parent':str(path.parent),'folders':children,
                'free':shutil.disk_usage(path).free}

    def _available(self):
        if self.closed:raise RuntimeError('The model library is shutting down.')
        if self.worker and self.worker.is_alive():raise RuntimeError('Wait for the current model operation to finish or cancel it.')

    def _check(self):
        if self.cancel_event.is_set():raise Cancelled()

    def _publish(self, **values):
        with self.lock:self.state.update(values)

    def download_target(self, family, component):
        """Download all weights for one model into a single named directory."""
        destination = self.data['destination']
        if not destination:
            return None
        organized = Path(destination) / MODEL_SET_DIRECTORIES[family] / component['filename']
        legacy = Path(destination) / family / component['filename']
        # Existing in-progress downloads must keep their resumable .part files.
        # Fresh downloads always use the readable directory names.
        if (not organized.exists() and not organized.with_name(organized.name+'.part').exists()
                and (legacy.exists() or legacy.with_name(legacy.name+'.part').exists())):
            return legacy
        return organized

    def find_lora(self, family, diffusion=None):
        """Locate a model adapter in registered folders without moving files.

        Prefer the imported generator's adapter, then organized downloads.
        Legacy locations remain supported; no expensive recursive scan is
        required when one of the conventional locations already has it.
        """
        component = next((part for part in self.manifest[family]
                          if part['role'] == 'lora'), None)
        if component is None:
            return None
        name = component['filename']
        with self.lock:
            roots = [Path(root) for root in self.data['roots']]
            destination = self.data['destination']
            verified = self.verifications()
        seen = set()

        def valid(path):
            path = Path(path)
            if path in seen or '.popai-trash' in path.parts:
                return False
            seen.add(path)
            try:
                return (path.is_file() and not path.is_symlink()
                        and any(path.resolve().is_relative_to(root) for root in roots)
                        and verified.get(str(path), {}).get('integrity') != 'failed')
            except OSError:
                return False

        candidates = []
        if diffusion:
            candidates.append(Path(diffusion).parent / name)
        if destination:
            candidates.extend((Path(destination) / MODEL_SET_DIRECTORIES[family] / name,
                               Path(destination) / family / name))
        for candidate in candidates:
            if valid(candidate):
                return candidate
        for root in roots:
            if not root.is_dir():
                continue
            try:
                for candidate in root.rglob(name):
                    if valid(candidate):
                        return candidate
            except OSError:
                continue
        return None

    def start(self, action, families, present):
        if action not in ('download','verify'):raise ValueError('Invalid operation.')
        if not isinstance(families,list) or not families or len(families)>len(self.manifest) or any(not isinstance(f,str) or f not in self.manifest for f in families):
            raise ValueError('Select models that are available in the library.')
        families=list(dict.fromkeys(families))
        with self.lock:
            self._available()
            destination=Path(self.data['destination']) if self.data['destination'] else None
            if action=='download' and (not destination or not destination.is_dir()):
                raise ValueError('Choose a download folder first.')
            tasks=[]
            for family in families:
                for component in self.manifest[family]:
                    current=present.get(family,{}).get(component['role'])
                    if action=='download' and current:continue
                    if action=='verify' and not current:raise ValueError('Locate all components before running verification.')
                    target=Path(current) if current else self.download_target(family, component)
                    tasks.append((family,component,target))
            needed=sum(max(0,c['size']-(p.with_name(p.name+'.part').stat().st_size if p.with_name(p.name+'.part').is_file() else 0)) for _,c,p in tasks) if action=='download' else 0
            if destination and action=='download' and shutil.disk_usage(destination).free < needed+64*1024**2:
                raise ValueError('There is not enough space in the selected folder.')
            self.cancel_event.clear()
            self.state={'state':'running','action':action,'families':families,'completed':0,'total':sum(p.stat().st_size if action=='verify' else c['size'] for _,c,p in tasks),'file':'','phase':'preparing','results':[]}
            self.worker=threading.Thread(target=self._run,args=(action,tasks),daemon=True)
            self.worker.start()
        return self.snapshot()

    def _hash(self,path):
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            while chunk:=stream.read(2*1024**2):
                self._check();digest.update(chunk)
        self._check()
        return digest.hexdigest()

    def _download(self, component, target, completed):
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            # Never overwrite an existing file, including imported files.
            if target.stat().st_size!=component['size'] or self._hash(target)!=component['sha256']:
                raise ValueError(f'A different file already exists at {target}. Choose another folder or move that file.')
            return False
        partial=target.with_name(target.name+'.part')
        if partial.is_symlink() or target.is_symlink():raise ValueError('The destination cannot be a symbolic link.')
        offset=partial.stat().st_size if partial.exists() else 0
        if offset>component['size']:raise ValueError(f'Invalid partial download: {partial}')
        if offset<component['size']:
            headers={'User-Agent':'popAI-model-library/1','Accept-Encoding':'identity'}
            if offset:headers['Range']=f'bytes={offset}-'
            with urlopen(Request(component['url'],headers=headers),timeout=15) as response:
                if response.status==206:
                    match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',response.headers.get('Content-Range',''))
                    if not match or int(match[1])!=offset or int(match[3])!=component['size'] or int(match[2])!=component['size']-1:
                        raise ValueError('The server returned an invalid response when resuming the download.')
                elif response.status==200:offset=0
                else:raise ValueError('The server refused the download.')
                declared=response.headers.get('Content-Length')
                if declared is not None and int(declared)!=component['size']-offset:
                    raise ValueError('The file size reported by the server does not match the model.')
                with partial.open('ab' if offset else 'wb') as output:
                    while True:
                        self._check()
                        chunk=response.read(1024**2)
                        if not chunk:break
                        if offset+len(chunk)>component['size']:raise ValueError('The download is larger than expected.')
                        output.write(chunk);offset+=len(chunk)
                        self._publish(completed=completed+offset)
                    output.flush();os.fsync(output.fileno())
        if partial.stat().st_size!=component['size']:raise ValueError('The download is incomplete. Try again to resume it.')
        self._publish(phase='verifying')
        if self._hash(partial)!=component['sha256']:
            partial.unlink()
            raise ValueError('SHA-256 verification failed. Download the component again.')
        self._check()
        # Hard link provides no-clobber publication on the same filesystem.
        try:
            os.link(partial,target)
            partial.unlink()
        except OSError as exc:
            if exc.errno not in (errno.EPERM,errno.EOPNOTSUPP,errno.ENOSYS):raise
            # FAT/exFAT may not support links. Linux renameat2 still publishes
            # atomically with RENAME_NOREPLACE, preserving existing files.
            libc=ctypes.CDLL(None,use_errno=True)
            rename=getattr(libc,'renameat2',None)
            if rename is None:raise OSError('The app cannot safely save the model in this folder. Choose another folder.') from exc
            rename.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint]
            rename.restype=ctypes.c_int
            if rename(-100,os.fsencode(partial),-100,os.fsencode(target),1)!=0:
                error=ctypes.get_errno();raise OSError(error,os.strerror(error),str(target))
        return True

    def _run(self, action, tasks):
        completed=0
        results=[]
        try:
            for family,component,target in tasks:
                self._check()
                self._publish(file=target.name,phase='downloading' if action=='download' else 'verifying',completed=completed)
                owned=False
                if action=='download':
                    owned=self._download(component,target,completed)
                    digest=component['sha256']
                else:
                    before=target.stat()
                    digest=self._hash(target)
                    after=target.stat()
                    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                        raise ValueError(f'{target.name} changed during verification. Try again.')
                st=target.stat()
                official=st.st_size==component['size'] and digest==component['sha256']
                with self.lock:
                    old=self.data['managed'].get(str(target))
                    previous=self.data['verified'].get(str(target))
                    reference=old or (previous if previous and (previous.get('official') or previous.get('integrity')=='failed') else None)
                    if reference and digest!=reference['sha256']:
                        self.data['verified'][str(target)]={'family':family,'role':component['role'],'sha256':reference['sha256'],'actual_sha256':digest,'size':st.st_size,'mtime_ns':st.st_mtime_ns,'official':bool(reference.get('official',old is not None)),'integrity':'failed'}
                        self._save()
                        raise ValueError(f'{target.name} differs from the previously verified file. The app kept the file.')
                    if action=='verify':
                        if component['role']=='lora':
                            info=model_catalog.inspect(target)
                            if (info['format']!='safetensors'
                                    or not any('.lora_' in name.lower() for name in info['tensors'])):
                                raise ValueError('The Turbo LoRA is not a valid LoRA safetensors file.')
                        else:
                            model_catalog.validate(family,{component['role']:target})
                    unchanged=previous['sha256']==digest if previous else None
                    integrity='official' if official else 'local' if unchanged else 'changed' if previous else 'unconfirmed'
                    record={'family':family,'role':component['role'],'sha256':digest,'size':st.st_size,'mtime_ns':st.st_mtime_ns,'official':official,'integrity':integrity}
                    self.data['verified'][str(target)]=record
                    if owned or old:
                        self.data['managed'][str(target)]={'family':family,'role':component['role'],'sha256':digest,'size':st.st_size,'mtime_ns':st.st_mtime_ns,'directory':str(target.parent)}
                    self._save()
                results.append({'path':str(target),'integrity':integrity})
                completed+=st.st_size if action=='verify' else component['size']
                self._publish(completed=completed,results=list(results))
            message='Download complete.'
            if action=='verify':
                kinds={r['integrity'] for r in results}
                message=('The components are compatible. The original checksums for the alternative files are unknown.' if kinds & {'unconfirmed','changed'} else
                         'The components are compatible. The alternative files match the last verification.' if 'local' in kinds else
                         'The default components passed SHA-256 verification.')
            self._publish(state='done',phase='done',file='',message=message)
        except Cancelled:self._publish(state='cancelled',phase='cancelled')
        except Exception as exc:self._publish(state='error',error=str(exc))

    def cancel(self):
        self.cancel_event.set()
        return self.snapshot()

    def remove(self,family):
        if not isinstance(family,str) or family not in self.manifest:raise ValueError('Invalid model.')
        with self.lock:
            self._available()
            records=[(Path(p),r) for p,r in self.data['managed'].items() if r['family']==family]
            if not records:raise ValueError('There are no files downloaded by the app to remove.')
            # Move only unchanged registered downloads into recoverable trash.
            for path,r in records:
                if path.parent!=Path(r['directory']) or path.is_symlink():raise ValueError('Invalid file record.')
                if path.exists():
                    stat=path.stat()
                    if stat.st_size!=r['size'] or stat.st_mtime_ns!=r['mtime_ns']:
                        raise ValueError('A file changed outside the app. The app kept the file.')
            for path,r in records:
                if path.exists():
                    trash=path.parent/'.popai-trash'/uuid.uuid4().hex
                    trash.mkdir(parents=True)
                    os.replace(path,trash/path.name)
                self.data['managed'].pop(str(path))
                self.data['verified'].pop(str(path),None)
            self._save()
        return self.snapshot()

    def close(self):
        with self.lock:self.closed=True
        self.cancel_event.set()
        if self.worker:self.worker.join(timeout=20)
