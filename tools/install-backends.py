#!/usr/bin/env python3
"""Install a pinned precompiled native bundle. Never invoke a compiler."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile

from fetch import fetch

ROOT=Path(__file__).resolve().parents[1]
PLATFORM='linux-x86_64-v3'
ARCHIVE='popai-backends-linux-x86_64-v3.tar.gz'
BINARIES={
 'stable-diffusion.cpp/build/bin/sd-cli',
 'stable-diffusion.cpp/build/bin/sd-server',
 'llama-vulkan/llama-server',
 'upscayl-ncnn/upscayl-bin',
 'upscayl-ncnn/upscayl-chain',
 'process-guard','vulkan-probe',
}
LICENSES={'POPAI_LICENSE','llama-vulkan/LICENSE','llama-vulkan/THIRD_PARTY_LICENSES.txt',
          'stable-diffusion.cpp/THIRD_PARTY_LICENSES.txt','stable-diffusion.cpp/ggml/THIRD_PARTY_LICENSES.txt',
          'upscayl-ncnn/LICENSE','upscayl-ncnn/CHAIN_LICENSES.txt'}
MANIFEST='bundle-manifest.json'
SOURCE_FILES=('sources.json','prompt-enhancer.json')

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def clean_relative(name):
    if not isinstance(name,str) or not name or '\\' in name or any(p in ('','.','..') for p in name.split('/')):
        raise ValueError(f'Unsafe archive path: {name!r}')
    p=PurePosixPath(name)
    if p.is_absolute() or str(p)!=name:raise ValueError(f'Unsafe archive path: {name!r}')
    return p

def record_ok(record):
    return (isinstance(record,dict) and type(record.get('size')) is int and record['size']>0
            and isinstance(record.get('sha256'),str) and re.fullmatch('[0-9a-f]{64}',record['sha256']))

def sources(root):
    return {name:sha(root/name) for name in SOURCE_FILES}

def config(root):
    path=root/'backend-bundle.json'
    if not path.is_file():raise ValueError('No verified precompiled bundle is pinned for this checkout. Use a published release.')
    data=json.loads(path.read_text())
    if (not record_ok(data) or data.get('format')!=1 or data.get('archive')!=ARCHIVE
        or data.get('platform')!=PLATFORM or data.get('glibc_min')!='2.39'
        or data.get('source_sha256')!=sources(root)
        or not isinstance(data.get('manifest_sha256'),str) or not re.fullmatch('[0-9a-f]{64}',data['manifest_sha256'])):
        raise ValueError('Precompiled bundle metadata does not match the pinned source revisions.')
    url=data.get('url','')
    if not isinstance(url,str) or not re.fullmatch(r'https://github\.com/usr-kmasx/popAI/releases/download/[A-Za-z0-9._-]+/'+re.escape(ARCHIVE),url):
        raise ValueError('Invalid pinned backend release URL.')
    return data

def required_files(root):
    return {entry['file'].removeprefix('backends/'):entry
            for entry in json.loads((root/'sources.json').read_text())['upscaler']['files']}

def allowed(name,required):
    return (name in BINARIES or name in LICENSES or name in required
            or re.fullmatch(r'(?:stable-diffusion\.cpp/build/bin|llama-vulkan)/lib[^/]+\.so(?:\.[0-9]+)*',name))

def validate_manifest(data,root):
    if (not isinstance(data,dict) or data.get('format')!=1 or data.get('platform')!=PLATFORM
        or data.get('glibc_min')!='2.39' or data.get('source_sha256')!=sources(root)
        or not isinstance(data.get('files'),dict)):
        raise ValueError('Invalid native bundle manifest.')
    files=data['files'];required=required_files(root)
    if not (BINARIES|LICENSES|set(required)).issubset(files):
        raise ValueError('Incomplete native bundle.')
    if len(files)>256:raise ValueError('Too many bundle files.')
    for name,item in files.items():
        clean_relative(name)
        if not allowed(name,required) or not record_ok(item) or type(item.get('executable')) is not bool:
            raise ValueError(f'Unexpected bundle file: {name}')
        if name in BINARIES and not item['executable']:raise ValueError(f'Non-executable backend: {name}')
        if name in required and any(item[key]!=required[name][key] for key in ('size','sha256')):
            raise ValueError(f'Upstream asset mismatch: {name}')
    if sum(item['size'] for item in files.values())>2*1024**3:
        raise ValueError('Native bundle is too large.')
    return files

def verified_file(path,item):
    return (path.is_file() and not path.is_symlink() and path.stat().st_size==item['size'] and sha(path)==item['sha256'])

def verify_tree(directory,root,record):
    if directory.is_symlink() or not directory.is_dir():raise ValueError('Backend directory is missing or unsafe.')
    manifest_path=directory/MANIFEST
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size>1024*1024:
        raise ValueError('Native bundle manifest is missing.')
    if sha(manifest_path)!=record['manifest_sha256']:
        raise ValueError('Installed bundle manifest does not match the pinned archive.')
    manifest=json.loads(manifest_path.read_text())
    files=validate_manifest(manifest,root)
    actual=set()
    for path in directory.rglob('*'):
        if path.is_symlink():raise ValueError(f'Unexpected symlink in installed bundle: {path}')
        if path.is_file():actual.add(path.relative_to(directory).as_posix())
        elif not path.is_dir():raise ValueError(f'Unexpected special file: {path}')
    if actual!=set(files)|{MANIFEST}:raise ValueError('Backend directory has unexpected or missing files.')
    for name,item in files.items():
        path=directory/name
        if not verified_file(path,item) or bool(path.stat().st_mode&0o111)!=item['executable']:
            raise ValueError(f'Corrupted or modified backend file: {name}')
    return manifest

def extract_archive(archive,stage,root,record):
    if not verified_file(archive,record):raise ValueError('Backend archive failed SHA-256/size verification.')
    with tarfile.open(archive,'r:gz') as tar:
        members=tar.getmembers()
        if len(members)>512:raise ValueError('Too many archive entries.')
        names=set()
        for member in members:
            path=clean_relative(member.name.rstrip('/') if member.isdir() else member.name)
            if path.parts[0]!='backends' or (len(path.parts)==1 and not member.isdir()) or not (member.isfile() or member.isdir()):
                raise ValueError(f'Unsafe archive entry: {member.name}')
            if path in names:raise ValueError(f'Duplicate archive entry: {member.name}')
            names.add(path)
        manifest_member=tar.getmember('backends/'+MANIFEST)
        if not manifest_member.isfile() or manifest_member.size>1024*1024:raise ValueError('Invalid archive manifest.')
        with tar.extractfile(manifest_member) as stream:manifest=json.load(stream)
        files=validate_manifest(manifest,root)
        payload={m.name.removeprefix('backends/'):m for m in members if m.isfile() and m.name!='backends/'+MANIFEST}
        if set(payload)!=set(files):raise ValueError('Archive payload differs from its manifest.')
        for name,member in payload.items():
            if member.size!=files[name]['size']:raise ValueError(f'Unexpected file size: {name}')
        tar.extractall(stage,filter='data')
    destination=stage/'backends'
    # Normalize executable bits independently of umask/archive ownership.
    for name,item in files.items():(destination/name).chmod(0o755 if item['executable'] else 0o644)
    verify_tree(destination,root,record)
    return destination

def install(root,record,archive_override=None):
    destination=root/'backends'
    if destination.exists() or destination.is_symlink():
        try:verify_tree(destination,root,record)
        except (OSError,ValueError) as exc:
            raise ValueError('Existing backend directory preserved. Move the old backends directory aside before installing the verified bundle. Details: '+str(exc)) from exc
        print('[popAI] Verified precompiled backends already installed.')
        return
    if archive_override is not None:
        archive=Path(archive_override).resolve()
    else:
        archive=root/'tools/downloads'/record['archive']
        archive.parent.mkdir(parents=True,exist_ok=True)
        if archive.is_symlink():raise ValueError('Archive cache must not be a symbolic link.')
        if archive.exists():
            if not verified_file(archive,record):raise ValueError('Existing archive has wrong SHA-256/size and was preserved.')
        else:
            partial=archive.with_name(archive.name+'.part')
            if verified_file(partial,record):partial.replace(archive)
            else:fetch(record['url'],archive,record['sha256'],expected_size=record['size'],resume=True)
    with tempfile.TemporaryDirectory(prefix='.popai-install-',dir=root) as temp:
        staged=extract_archive(archive,Path(temp),root,record)
        if destination.exists() or destination.is_symlink():raise ValueError('Backend destination appeared during installation; preserved.')
        staged.rename(destination)
    if archive_override is None:
        archive.unlink()
        try:archive.parent.rmdir()
        except OSError:pass
    print('[popAI] All seven precompiled native executables verified and installed.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--check',action='store_true')
    modes.add_argument('--archive',type=Path,help='Use a local copy of the exact pinned archive')
    args=parser.parse_args()
    try:
        record=config(ROOT)
        if args.check:verify_tree(ROOT/'backends',ROOT,record)
        else:install(ROOT,record,args.archive)
    except (ValueError,OSError,tarfile.TarError) as exc:
        parser.exit(1,f'[popAI] {exc}\n')
if __name__=='__main__':main()
