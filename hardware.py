"""Vulkan-only device selection; memory placement is handled by the native engine."""
import json
import os
import re
import subprocess
from app_config import APP_ROOT, HARDWARE_DEFAULTS

GiB = 1024 ** 3


def normalize(settings):
    if not isinstance(settings, dict) or set(settings) - set(HARDWARE_DEFAULTS):
        raise ValueError('Invalid hardware settings.')
    value = {**HARDWARE_DEFAULTS, **settings}
    for key in ('device', 'upscale_device'):
        choice = value[key]
        if not isinstance(choice, str) or not (choice == 'auto' or re.fullmatch(r'\d+', choice)):
            raise ValueError('Select Auto or enter the GPU Vulkan index.')
    if value['compatibility'] not in ('auto', 'on', 'off'):
        raise ValueError('Set compatibility to Auto, On, or Off.')
    return value


def environment():
    env = dict(os.environ)
    env['VK_LOADER_LAYERS_DISABLE'] = '~implicit~'
    # App policy controls these, without inheriting stale shell overrides.
    for key in ('GGML_VK_VISIBLE_DEVICES', 'GGML_VK_MAX_NODES_PER_SUBMIT', 'GGML_VK_SERIALIZE_SUBMISSIONS'):
        env.pop(key, None)
    env['XDG_CACHE_HOME'] = str(APP_ROOT / 'tools/cache')
    return env


def discover(executable):
    env = environment()
    try:
        native = subprocess.run([str(APP_ROOT / 'backends/vulkan-probe')], capture_output=True, text=True, env=env, timeout=20, check=True)
        devices = json.loads(native.stdout)
        ggml = subprocess.run([str(executable), '--list-devices'], capture_output=True, text=True, env=env, timeout=30, check=True)
        mapping = re.findall(r'^(Vulkan\d+)\t(.+)$', ggml.stdout, re.M)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise RuntimeError(f'Could not query Vulkan. Check the GPU driver. Details: {exc}') from exc
    for device in devices:
        matches = [key for key, name in mapping if name == device['name']]
        physical = [d for d in devices if d['name'] == device['name']]
        device['ggml'] = matches[0] if len(matches) == len(physical) == 1 else None
        device['usable'] = device['type'] in (1, 2) and bool(device['ggml'])
    return devices


def select(devices, settings):
    settings = normalize(settings)
    usable = [d for d in devices if d['usable']]
    def pick(choice):
        if choice == 'auto':
            if not usable:
                raise ValueError('The backends found no compatible Vulkan GPU. Check the GPU driver.')
            return max(usable, key=lambda d: (d['type'] == 2, d['free'] if d['free'] is not None else d['total']))
        matches = [d for d in devices if str(d['index']) == choice and d['type'] in (1, 2)]
        if not matches:
            raise ValueError('The selected GPU is unavailable.')
        if not matches[0]['ggml']:
            raise ValueError('The generator cannot uniquely match the GPU to a Vulkan device. Use GPUs with distinct names or disable the other GPU in the driver.')
        return matches[0]
    generator, upscaler = pick(settings['device']), pick(settings['upscale_device'])
    compatibility = settings['compatibility'] == 'on' or (settings['compatibility'] == 'auto' and 'POLARIS' in generator['name'].upper() and 'RADV' in generator['name'].upper())
    env = environment()
    if compatibility:
        env.update(GGML_VK_MAX_NODES_PER_SUBMIT='4', GGML_VK_SERIALIZE_SUBMISSIONS='1')
    return {'generator': generator, 'upscaler': upscaler, 'vram_limit': None, 'offload': 'ram',
            'compatibility': compatibility, 'free_known': generator['free'] is not None}, env
