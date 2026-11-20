"""Atomic job manifests for resuming only post-generation work."""
import copy
import json
import os
import re
import tempfile
from pathlib import Path
from app_config import portable_path, local_path

ID = re.compile(r'[0-9a-f]{32}')
PATH_FIELDS = ('diffusion','encoder','vae','vision','upscale_model')


def atomic_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name, suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class JobStore:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.directory = self.root / 'jobs'
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, job):
        if not ID.fullmatch(job['id']):
            raise ValueError('Invalid job ID.')
        data = copy.deepcopy(job)
        for key in PATH_FIELDS:
            if data.get('settings',{}).get(key):
                data['settings'][key] = portable_path(data['settings'][key], self.root)
        atomic_json(self.directory / (job['id']+'.json'), data)
        atomic_json(self.directory / 'latest.json', {'id':job['id']})

    def latest(self):
        try:
            identity = json.loads((self.directory/'latest.json').read_text())['id']
            if not isinstance(identity,str) or not ID.fullmatch(identity):
                return None
            data = json.loads((self.directory/(identity+'.json')).read_text())
            if data.get('id') != identity or data.get('version') != 1:
                return None
            for key in PATH_FIELDS:
                if data.get('settings',{}).get(key):
                    data['settings'][key] = str(local_path(data['settings'][key], self.root))
            return data
        except (OSError,ValueError,KeyError,TypeError):
            return None

