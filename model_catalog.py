"""Bounded header inspection; tensor weights are never read for identification."""
import functools
import json
import mmap
import struct
from pathlib import Path
from catalog import component_family

_LIMIT = 64 * 1024**2
_FORMATS = {0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}
_STRUCTS = {fmt:struct.Struct('<'+fmt) for fmt in set(_FORMATS.values())}


def inspect(path):
    path = Path(path).resolve()
    stat = path.stat()
    return _inspect(str(path), stat.st_size, stat.st_mtime_ns)


@functools.lru_cache(maxsize=256)
def _inspect(path, size, mtime):
    if size < 8:
        raise ValueError('Incomplete header.')
    # Map only the bounded header window; tensor weights are never touched.
    with open(path,'rb') as source, mmap.mmap(source.fileno(),min(size,_LIMIT),access=mmap.ACCESS_READ) as stream:
        position,limit = 0,min(size,_LIMIT)
        def read(count):
            nonlocal position
            end=position+count
            if count<0 or end>limit:
                raise ValueError('The header is too large or truncated.')
            result=stream[position:end]
            position=end
            return result
        def skip(count):
            nonlocal position
            if count<0 or position+count>limit:
                raise ValueError('The header is too large or truncated.')
            position+=count
        def number(fmt):
            nonlocal position
            decoder=_STRUCTS[fmt]
            if position+decoder.size>limit:
                raise ValueError('Incomplete header.')
            result=decoder.unpack_from(stream,position)[0]
            position+=decoder.size
            return result
        def string():
            length = number('Q')
            return read(length).decode('utf-8')
        def value(kind, depth=0):
            if kind in _FORMATS:
                return number(_FORMATS[kind])
            if kind == 8:
                return string()
            if kind == 9 and depth < 2:
                element, count = number('I'), number('Q')
                if count > 2_000_000:
                    raise ValueError('Invalid metadata array.')
                # Tokenizer arrays are not used to identify image components.
                # Skip their encoded payload instead of decoding every token.
                if element in _FORMATS:
                    skip(count*struct.calcsize('<'+_FORMATS[element]))
                elif element == 8:
                    for _ in range(count):
                        skip(number('Q'))
                else:
                    for _ in range(count):
                        value(element,depth+1)
                return None
            raise ValueError('Unrecognized GGUF type.')
        tensors, metadata = {}, {}
        try:
            magic = read(4)
            if magic == b'GGUF':
                if number('I') not in (2,3):
                    raise ValueError('Unsupported GGUF version.')
                count, fields = number('Q'), number('Q')
                if count > 100_000 or fields > 100_000:
                    raise ValueError('Invalid GGUF count.')
                for _ in range(fields):
                    key = string(); metadata[key] = value(number('I'))
                for _ in range(count):
                    name, dimensions = string(), number('I')
                    if not 1 <= dimensions <= 5:
                        raise ValueError('Invalid GGUF dimensions.')
                    shape = tuple(number('Q') for _ in range(dimensions))
                    kind, offset = number('I'), number('Q')
                    if offset >= size or any(d <= 0 for d in shape):
                        raise ValueError('Invalid GGUF tensor.')
                    tensors[name] = shape
                format_name = 'gguf'
            else:
                position = 0
                header = json.loads(read(number('Q')))
                if not isinstance(header, dict):
                    raise ValueError('Invalid Safetensors header.')
                metadata = header.get('__metadata__', {})
                for name, tensor in header.items():
                    if name == '__metadata__':
                        continue
                    shape = tensor.get('shape')
                    offsets = tensor.get('data_offsets')
                    if not isinstance(shape,list) or not isinstance(offsets,list) or len(offsets)!=2 or not 0 <= offsets[0] <= offsets[1] <= size-position:
                        raise ValueError('Invalid Safetensors tensor.')
                    tensors[name] = tuple(shape)
                format_name = 'safetensors'
            if not tensors:
                raise ValueError('The file contains no tensors.')
        except (struct.error, UnicodeError, KeyError, TypeError, AttributeError) as exc:
            raise ValueError('Invalid model header.') from exc
    return {'format':format_name, 'metadata':metadata, 'tensors':tensors, 'size':size}


def identify(data):
    t, meta = data['tensors'], data['metadata']
    arch = meta.get('general.architecture', '')
    if arch == 'qwen3' and t.get('token_embd.weight') == (2560,151936):
        return 'encoder', 'qwen3-4b'
    if arch == 'qwen3vl' and t.get('token_embd.weight') == (2560,151936):
        return 'encoder', 'qwen3vl-4b'
    if arch == 'qwen3vl' and t.get('token_embd.weight') == (4096,151936):
        return 'encoder', 'qwen3vl-8b'
    if arch == 'clip' and meta.get('clip.projector_type') == 'qwen3vl_merger' and t.get('v.patch_embd.weight') == (16,16,3,1152):
        return 'vision', 'qwen3vl-8b'
    if any(name.endswith('emb_in.image.weight') for name in t) and any(name.endswith('txt_mode_blocks.0.q_proj.weight') for name in t):
        return 'diffusion', 'flux3-klein'
    if t.get('img_in.weight') == (128,3072) and 'double_blocks.0.img_attn.qkv.weight' in t:
        return 'diffusion', 'klein'
    if t.get('model.diffusion_model.img_in.weight') == (64,4096) and 'model.diffusion_model.modulation.1.weight' in t:
        return 'diffusion', 'qwen'
    if t.get('x_embedder.weight') == (64,3840) and t.get('cap_embedder.1.weight') == (2560,3840):
        return 'diffusion', 'z-image-turbo'
    if t.get('decoder.conv_in.weight') == (512,32,3,3) and t.get('bn.running_mean') == (128,):
        return 'vae', 'klein'
    if t.get('decoder.conv_in.weight') == (512,16,3,3) and t.get('encoder.conv_out.weight') == (32,512,3,3):
        return 'vae', 'z-image-turbo'
    if t.get('decoder.conv1.weight') == (1152,64,1,3,3) and t.get('decoder.head.2.weight') == (4,144,1,3,3):
        return 'vae', 'qwen'
    # General role discovery is based on tensor structure/metadata, never filenames.
    names = tuple(name.lower() for name in t)
    architecture = str(arch or meta.get('architecture') or meta.get('model_type') or 'unknown')
    stripped = tuple(name.removeprefix('model.diffusion_model.').removeprefix('diffusion_model.') for name in names)
    if any('rdb' in name and 'conv' in name for name in names):
        return 'upscaler', architecture if architecture!='unknown' else 'esrgan'
    if any(name.startswith(('decoder.','first_stage_model.decoder.')) for name in names) and any(name.startswith(('encoder.','first_stage_model.encoder.')) for name in names):
        if not any(name.startswith('model.diffusion_model.') for name in names):
            return 'vae', architecture
    if any(name.startswith(('v.blk.','v.patch_embd','vision_model.','visual.','vision_tower.','mm_projector.')) for name in names) and not any('token_embd.weight' in name or 'embed_tokens.weight' in name for name in names):
        return 'vision', architecture
    if any(name.startswith(('model.diffusion_model.','diffusion_model.')) for name in names) or any(name.startswith(('double_blocks.','single_blocks.','joint_blocks.','transformer_blocks.','input_blocks.','down_blocks.','x_embedder.','img_in.','patch_embed.')) for name in stripped):
        return 'diffusion', architecture
    if any('token_embd.weight' in name or 'embed_tokens.weight' in name or 'token_embedding.weight' in name or name.startswith(('text_model.','t5.encoder.','encoder.block.')) for name in names):
        return 'encoder', architecture
    return 'unknown', architecture


def diffusion_profile(path, data=None):
    role,family = identify(data or inspect(path))
    if role not in ('diffusion','unknown'):
        raise ValueError('Select a generator in the Generator field.')
    if family == 'qwen':
        return 'qwen-turbo' if 'turbo' in Path(path).name.lower() else 'qwen'
    return family if family in ('klein','z-image-turbo','flux3-klein') else 'auto'


def validate(profile, paths):
    family = 'qwen' if profile in ('qwen','qwen-turbo') else profile
    expected = {'diffusion': family, 'encoder': 'qwen3vl-8b' if family == 'qwen' else 'qwen3-4b', 'vae': family, 'vision':'qwen3vl-8b'}
    if family=='flux3-klein':
        expected.update({role:component_family(family,role) for role in ('encoder','vae')})
    for role, path in paths.items():
        if path is None or (role == 'vision' and family != 'qwen'):
            continue
        try:
            actual = identify(inspect(path))
        except (OSError, ValueError) as exc:
            raise ValueError(f'Could not identify the {role} component in {Path(path).name}. {exc}') from exc
        if profile == 'auto':
            if actual[0] not in (role,'unknown'):
                raise ValueError(f'{Path(path).name} is a {actual[0]} component. Select a {role} component.')
            continue
        if actual != (role, expected[role]):
            raise ValueError(f'{Path(path).name} was identified as {actual[0]} / {actual[1]}. Select a {role} / {expected[role]} component.')


def validate_upscaler(path):
    path = Path(path)
    if path.suffix != '.bin' or path.stat().st_size < 1024:
        raise ValueError('Invalid NCNN weights.')
    param = path.with_suffix('.param')
    if param.stat().st_size > 2*1024**2:
        raise ValueError('Invalid NCNN .param file.')
    lines = param.read_text().splitlines()
    if len(lines) < 3 or lines[0].strip() != '7767517':
        raise ValueError('The .param file is not a valid NCNN model.')
    counts = lines[1].split()
    if len(counts) != 2 or not all(v.isdigit() and int(v)>0 for v in counts):
        raise ValueError('Invalid NCNN header.')
