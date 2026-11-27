"""Offline installer tests. Tiny synthetic archives, no real model downloads."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
spec=importlib.util.spec_from_file_location('install_backends',ROOT/'tools/install-backends.py')
installer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

class BackendInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.payload={name:b'fixture: '+name.encode() for name in installer.BINARIES|installer.LICENSES}
        self.payload.update({'upscayl-ncnn/models/realesrgan-x4plus.bin':b'fake weights',
                             'upscayl-ncnn/models/realesrgan-x4plus.param':b'fake params',
                             'llama-vulkan/libllama.so.1':b'fake shared library'})
        pinned=[]
        for name in ('upscayl-ncnn/models/realesrgan-x4plus.bin','upscayl-ncnn/models/realesrgan-x4plus.param','upscayl-ncnn/upscayl-bin'):
            pinned.append({'file':'backends/'+name,**self.record(self.payload[name])})
        (self.root/'sources.json').write_text(json.dumps({'upscaler':{'files':pinned}}))
        (self.root/'prompt-enhancer.json').write_text('{}')
        self.manifest={'format':1,'platform':installer.PLATFORM,'glibc_min':'2.39',
            'source_sha256':installer.sources(self.root),
            'files':{name:{**self.record(data),'executable':name in installer.BINARIES} for name,data in self.payload.items()}}
        self.archive=self.root/installer.ARCHIVE
        self.make_archive()
    @staticmethod
    def record(data):
        return {'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    def make_archive(self,extra=None,omit=None,manifest=None):
        manifest=self.manifest if manifest is None else manifest
        manifest_bytes=json.dumps(manifest).encode()
        with tarfile.open(self.archive,'w:gz') as tar:
            def add(name,data):
                item=tarfile.TarInfo(name);item.size=len(data);item.mode=0o644
                tar.addfile(item,io.BytesIO(data))
            add('backends/'+installer.MANIFEST,manifest_bytes)
            for name,data in self.payload.items():
                if name!=omit:add('backends/'+name,data)
            if extra:extra(tar)
        self.config={'format':1,'archive':installer.ARCHIVE,'platform':installer.PLATFORM,'glibc_min':'2.39',
            'source_sha256':installer.sources(self.root),'manifest_sha256':self.record(manifest_bytes)['sha256'],
            'url':'https://github.com/usr-kmasx/popAI/releases/download/backend-test/'+installer.ARCHIVE,
            **self.record(self.archive.read_bytes())}
        (self.root/'backend-bundle.json').write_text(json.dumps(self.config))
    def install(self):
        installer.install(self.root,installer.config(self.root),self.archive)
    def test_fresh_install_idempotent_and_preserves_archive(self):
        self.install()
        before=(self.root/'backends'/installer.MANIFEST).read_bytes()
        self.install()
        self.assertEqual((self.root/'backends'/installer.MANIFEST).read_bytes(),before)
        self.assertTrue(self.archive.is_file())
        installer.verify_tree(self.root/'backends',self.root,self.config)
        self.assertFalse(list(self.root.glob('.popai-install-*')))
    def test_modified_binary_and_manifest_cannot_be_accepted(self):
        self.install()
        path=self.root/'backends'/'process-guard'
        path.write_bytes(b'modified')
        with self.assertRaises(ValueError):self.install()
        manifest=self.root/'backends'/installer.MANIFEST
        data=json.loads(manifest.read_text());data['files']['process-guard'].update(self.record(b'modified'))
        manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):self.install()
        self.assertEqual(path.read_bytes(),b'modified')
    def test_archive_hash_mismatch_no_files_extracted(self):
        self.archive.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):self.install()
        self.assertFalse((self.root/'backends').exists())
    def test_path_traversal_absolute_and_symlink_rejected(self):
        for name,kind in (('backends/../escape',tarfile.REGTYPE),('/tmp/escape',tarfile.REGTYPE),('backends/escape',tarfile.SYMTYPE),('backends/escape',tarfile.LNKTYPE)):
            with self.subTest(name=name,kind=kind):
                def extra(tar):
                    item=tarfile.TarInfo(name);item.type=kind;item.linkname='/etc/passwd'
                    tar.addfile(item)
                self.make_archive(extra=extra)
                with self.assertRaises(ValueError):self.install()
                self.assertFalse((self.root/'backends').exists())
                self.assertFalse((self.root/'escape').exists())
    def test_duplicate_entry_rejected(self):
        def extra(tar):
            tar.addfile(tarfile.TarInfo('backends/process-guard'))
        self.make_archive(extra=extra)
        with self.assertRaises(ValueError):self.install()
        self.assertFalse((self.root/'backends').exists())
    def test_missing_backend_rejected(self):
        self.make_archive(omit='process-guard')
        with self.assertRaises(ValueError):self.install()
        self.assertFalse((self.root/'backends').exists())
    def test_unexpected_payload_rejected(self):
        def extra(tar):tar.addfile(tarfile.TarInfo('backends/extra.txt'))
        self.make_archive(extra=extra)
        with self.assertRaises(ValueError):self.install()
        self.assertFalse((self.root/'backends').exists())
    def test_pinned_upstream_hash_mismatch_rejected(self):
        self.payload['upscayl-ncnn/upscayl-bin']=b'not original'
        self.manifest['files']['upscayl-ncnn/upscayl-bin'].update(self.record(b'not original'))
        self.make_archive()
        with self.assertRaises(ValueError):self.install()
    def test_preserves_legacy_install(self):
        backend=self.root/'backends';backend.mkdir();(backend/'user-data').write_text('keep')
        with self.assertRaises(ValueError):self.install()
        self.assertEqual((backend/'user-data').read_text(),'keep')
    def test_pinned_revisions_mismatch(self):
        (self.root/'prompt-enhancer.json').write_text('{"new":true}')
        with self.assertRaises(ValueError):self.install()
    def test_wrong_inner_manifest_hash(self):
        self.config['manifest_sha256']='0'*64
        (self.root/'backend-bundle.json').write_text(json.dumps(self.config))
        with self.assertRaises(ValueError):self.install()
        self.assertFalse((self.root/'backends').exists())
    def test_download_verified_then_archive_removed(self):
        def download(url,destination,sha256,**kw):
            self.assertEqual(sha256,self.config['sha256'])
            destination.write_bytes(self.archive.read_bytes())
        with patch.object(installer,'fetch',side_effect=download) as call:
            installer.install(self.root,self.config)
            call.assert_called_once()
        installer.verify_tree(self.root/'backends',self.root,self.config)
        self.assertFalse((self.root/'tools/downloads'/installer.ARCHIVE).exists())
if __name__=='__main__':unittest.main()
