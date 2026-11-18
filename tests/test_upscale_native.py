"""CPU regression test for pixel-unshuffle alignment across ESRGAN tiles."""
import array
import json
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / 'backends/stable-diffusion.cpp/build/bin/sd-cli'


def write_fixture_model(path):
    headers, parts, offset = {}, [], 0

    def tensor(name, shape, identity=False):
        nonlocal offset
        count = 1
        for dimension in shape:
            count *= dimension
        data = array.array('f', [0.0]) * count
        if identity:
            for channel in range(shape[0] if name.startswith('conv_last') else 1):
                data[channel * shape[1] * 9 + 4] = 1.0
        raw = data.tobytes()
        headers[name] = {'dtype': 'F32', 'shape': shape, 'data_offsets': [offset, offset + len(raw)]}
        offset += len(raw)
        parts.append(raw)

    for name, incoming, outgoing, identity in [
        ('conv_first', 12, 64, True), ('conv_body', 64, 64, False),
        ('conv_up1', 64, 64, True), ('conv_up2', 64, 64, True),
        ('conv_hr', 64, 64, True), ('conv_last', 64, 3, True),
    ]:
        tensor(name + '.weight', [outgoing, incoming, 3, 3], identity)
        tensor(name + '.bias', [outgoing])
    for block in range(1, 4):
        for layer in range(1, 6):
            name = f'body.0.rdb{block}.conv{layer}'
            outgoing = 64 if layer == 5 else 32
            tensor(name + '.weight', [outgoing, 64 + (layer - 1) * 32, 3, 3])
            tensor(name + '.bias', [outgoing])
    header = json.dumps(headers).encode()
    header += b' ' * (-len(header) % 8)
    path.write_bytes(struct.pack('<Q', len(header)) + header + b''.join(parts))


def write_rgb(path, width, height):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    rows = b''.join(b'\0' + bytes(value for x in range(width) for value in (x * 10 + y, 0, 0)) for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def read_rgb(path):
    data, position, compressed = path.read_bytes(), 8, b''
    while position < len(data):
        size = struct.unpack('>I', data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        payload = data[position + 8:position + 8 + size]
        if kind == b'IHDR':
            width, height, depth, color, _, _, interlace = struct.unpack('>IIBBBBB', payload)
            assert (depth, color, interlace) == (8, 2, 0)
        if kind == b'IDAT':
            compressed += payload
        position += size + 12
    raw, stride, rows = zlib.decompress(compressed), width * 3, []
    previous = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        mode, row = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for x in range(stride):
            left, up, corner = (row[x - 3] if x >= 3 else 0), previous[x], (previous[x - 3] if x >= 3 else 0)
            predictor = 0
            if mode == 1: predictor = left
            elif mode == 2: predictor = up
            elif mode == 3: predictor = (left + up) // 2
            elif mode == 4:
                p = left + up - corner
                distances = (abs(p - left), abs(p - up), abs(p - corner))
                predictor = (left, up, corner)[distances.index(min(distances))]
            row[x] = (row[x] + predictor) & 255
        rows.append(row)
        previous = row
    return width, height, b''.join(rows)


@unittest.skipUnless(BINARY.exists(), 'Compile sd-cli first')
class NativeUpscaleTests(unittest.TestCase):
    def test_tiled_two_times_model_keeps_global_pixel_unshuffle_phase(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            model, source, output = (directory / name for name in ('model.safetensors', 'input.png', 'output.png'))
            write_fixture_model(model)
            write_rgb(source, 22, 18)
            result = subprocess.run([str(BINARY), '-M', 'upscale', '--upscale-model', str(model), '-i', str(source), '--backend', 'cpu', '--upscale-tile-size', '8', '-o', str(output)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            width, height, pixels = read_rgb(output)
            self.assertEqual((width, height), (44, 36))
            maximum_error = max(abs(pixels[(y * width + x) * 3 + channel] - ((x // 4) * 20 + (y // 4) * 2)) for y in range(height) for x in range(width) for channel in range(3))
            self.assertLessEqual(maximum_error, 1, 'tiles shifted the pixel-unshuffle grouping')
