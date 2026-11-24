"""Offline tests for pinned installer downloads and interrupted model transfers."""
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import fetch as downloader


class Response(io.BytesIO):
    def __init__(self, body, status=200, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'weights.gguf'
        self.full = b'model-weights-' * 100
        self.sha = hashlib.sha256(self.full).hexdigest()

    def tearDown(self):
        self.temp.cleanup()

    def test_fresh_download_only_publishes_after_hash(self):
        with patch.object(downloader, 'urlopen', return_value=Response(
                self.full, headers={'Content-Length': str(len(self.full))})):
            downloader.fetch('https://example.test/weights', self.path, self.sha,
                             expected_size=len(self.full), resume=True)
        self.assertEqual(self.path.read_bytes(), self.full)
        self.assertFalse(self.path.with_name(self.path.name + '.part').exists())

    def test_resume_with_correct_range_and_no_duplicate_bytes(self):
        size = len(self.full)
        partial = self.path.with_name(self.path.name + '.part')
        partial.write_bytes(self.full[:41])
        with patch.object(downloader, 'urlopen', return_value=Response(
                self.full[41:], status=206, headers={
                    'Content-Range': f'bytes 41-{size - 1}/{size}',
                    'Content-Length': str(size - 41),
                })) as opened:
            downloader.fetch('https://example.test/weights', self.path, self.sha,
                             expected_size=size, resume=True)
        self.assertEqual(opened.call_args.args[0].get_header('Range'), 'bytes=41-')
        self.assertEqual(self.path.read_bytes(), self.full)

    def test_server_ignores_range_and_full_download_replaces_partial(self):
        partial = self.path.with_name(self.path.name + '.part')
        partial.write_bytes(self.full[:33])
        with patch.object(downloader, 'urlopen', return_value=Response(
                self.full, headers={'Content-Length': str(len(self.full))})):
            downloader.fetch('https://example.test/weights', self.path, self.sha,
                             expected_size=len(self.full), resume=True)
        self.assertEqual(self.path.read_bytes(), self.full)

    def test_mismatched_range_preserves_existing_partial_and_destination(self):
        partial = self.path.with_name(self.path.name + '.part')
        partial.write_bytes(self.full[:33])
        self.path.write_bytes(b'existing')
        with patch.object(downloader, 'urlopen', return_value=Response(
                self.full[33:], status=206, headers={
                    'Content-Range': f'bytes 35-{len(self.full)-1}/{len(self.full)}',
                })):
            with self.assertRaisesRegex(ValueError, 'resume range'):
                downloader.fetch('https://example.test/weights', self.path, self.sha,
                                 expected_size=len(self.full), resume=True)
        self.assertEqual(self.path.read_bytes(), b'existing')
        self.assertEqual(partial.read_bytes(), self.full[:33])

    def test_incomplete_download_keeps_partial_only_in_resume_mode(self):
        body = self.full[:200]
        with patch.object(downloader, 'urlopen', return_value=Response(body)):
            with self.assertRaisesRegex(ValueError, 'Incomplete download'):
                downloader.fetch('https://example.test/weights', self.path, self.sha,
                                 expected_size=len(self.full), resume=True)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.path.with_name(self.path.name + '.part').read_bytes(), body)

    def test_bad_digest_does_not_publish_model(self):
        with patch.object(downloader, 'urlopen', return_value=Response(self.full)):
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                downloader.fetch('https://example.test/weights', self.path, '0' * 64,
                                 expected_size=len(self.full), resume=True)
        self.assertFalse(self.path.exists())
        self.assertFalse(self.path.with_name(self.path.name + '.part').exists())


if __name__ == '__main__':
    unittest.main()
