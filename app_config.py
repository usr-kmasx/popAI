"""Portable paths and versioned settings, independent of the launch directory."""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
RESOURCE_ROOT = Path(getattr(sys, '_MEIPASS', APP_ROOT))
COMPONENTS = ('diffusion', 'encoder', 'vae', 'vision')
HARDWARE_DEFAULTS = {'device': 'auto', 'upscale_device': 'auto', 'compatibility': 'auto'}


def local_path(value, root=APP_ROOT):
    path = Path(value).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def portable_path(value, root=APP_ROOT):
    if not value:
        return ''
    path = local_path(value, root)
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)


def normalize_roots(values, root=APP_ROOT):
    if not isinstance(values, list) or not values or len(values) > 32:
        raise ValueError('Enter between 1 and 32 model folders.')
    result = []
    for value in values:
        if not isinstance(value, str) or not value.strip() or '\0' in value:
            raise ValueError('Invalid model folder.')
        path = local_path(value.strip(), root)
        if path.exists() and not path.is_dir():
            raise ValueError(f'This path is not a folder: {path}')
        if path not in result:
            result.append(path)
    return result


class SettingsStore:
    def __init__(self, root=APP_ROOT):
        self.root = Path(root).resolve()
        self.path = self.root / 'model-settings.json'

    def check_writable(self):
        try:
            with tempfile.TemporaryFile(dir=self.root):
                pass
        except OSError as exc:
            raise OSError('The app folder is read-only. Move the app to a folder where you can save files.') from exc

    def load(self):
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('The saved settings are not a valid object.')
        version = data.get('schema_version', 1)
        if version not in (1, 2):
            raise ValueError('These settings are from a newer version of the app.')
        if version == 1:
            roots = []
            for key in COMPONENTS:
                if data.get(key):
                    path = local_path(data[key], self.root)
                    # Preserve the old external catalog when migrating the existing installation.
                    roots.append(next((parent for parent in path.parents if parent.name == 'IMG'), path.parent))
            data['model_roots'] = [str(p) for p in dict.fromkeys(roots)] or ['models']
            data['hardware'] = copy.deepcopy(HARDWARE_DEFAULTS)
            self.check_writable()
            backup = self.path.with_suffix('.v1-backup.json')
            if not backup.exists():
                backup.write_bytes(self.path.read_bytes())
            self.save(data)
        result = copy.deepcopy(data)
        if result.get('resolution') in ('720p', '900p'):
            result['resolution'] = '1080p'
        result['model_roots'] = [str(p) for p in normalize_roots(data.get('model_roots', ['models']), self.root)]
        for key in COMPONENTS:
            if result.get(key):
                result[key] = str(local_path(result[key], self.root))
        return result

    def save(self, settings):
        data = copy.deepcopy(settings)
        data['schema_version'] = 2
        data.pop('sd_default', None)
        data.pop('sd_defaults', None)
        for key in COMPONENTS:
            data[key] = portable_path(data.get(key, ''), self.root)
        data['model_roots'] = [portable_path(p, self.root) for p in data.get('model_roots', ['models'])]
        self.check_writable()
        fd, name = tempfile.mkstemp(prefix='.settings-', suffix='.tmp', dir=self.root)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                json.dump(data, output, ensure_ascii=False, indent=2)
                output.write('\n')
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)
