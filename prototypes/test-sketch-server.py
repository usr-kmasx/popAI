"""Minimal integration fixture for the real popAI HTTP routes, without loading image models."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import create_server

class FakeManager:
    def __init__(self):
        self.images = {}
        self.count = 0
    def status(self):
        return {
            'state': 'idle',
            'profile': 'flux-2-klein',
            'id': None,
            'phase': None,
            'models_ready': True,
            'enhancer': {'state': 'ready', 'busy': False},
        }
    def touch_references(self, ids):
        return []
    def store_reference(self, png):
        if not png.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValueError('Invalid PNG.')
        self.count += 1
        identity = f'{self.count:032x}'
        self.images[identity] = png
        return {'id': identity, 'image': f'/references/{identity}.png'}
    def release_references(self, ids):
        return {'released': len(ids or [])}
    def asset_bytes(self, identity, reference=False):
        return self.images.get(identity) if reference else None

if __name__ == '__main__':
    host = create_server(FakeManager(), 7863)
    try:
        host.serve_forever()
    finally:
        host.server_close()
