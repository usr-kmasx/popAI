#!/usr/bin/env python3
"""Build-only packager. Keep source trees, model LLM weights and toolchains out."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
BINARIES=(
 'stable-diffusion.cpp/build/bin/sd-cli',
 'stable-diffusion.cpp/build/bin/sd-server',
 'llama-vulkan/llama-server',
 'upscayl-ncnn/upscayl-bin',
 'upscayl-ncnn/upscayl-chain',
 'process-guard','vulkan-probe',
)
NAME='popai-backends-linux-x86_64-v3.tar.gz'
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    out=ROOT/'dist';out.mkdir(exist_ok=True)
    source=ROOT/'backends'
    with tempfile.TemporaryDirectory(prefix='popai-package-') as tmp:
        stage=Path(tmp)/'backends';stage.mkdir()
        def copy(rel,origin=None):
            dst=stage/rel
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(origin or source/rel,dst,follow_symlinks=True)
            return dst
        for rel in BINARIES:
            src=source/rel
            if not src.is_file() or not os.access(src,os.X_OK):
                raise RuntimeError(f'Missing executable: {rel}')
            copy(rel)
        sd=source/'stable-diffusion.cpp/build'
        sd_dest=stage/'stable-diffusion.cpp/build/bin'
        # All built shared libraries are colocated with both executables.
        for lib in sorted(sd.rglob('*.so*')):
            if lib.is_file() and re.fullmatch(r'lib[^/]+\.so(?:\.[0-9]+)*',lib.name):
                dst=sd_dest/lib.name
                if dst.exists() and sha(dst)!=sha(lib):raise RuntimeError(f'Conflicting shared library: {lib.name}')
                if not dst.exists():copy(str(dst.relative_to(stage)),lib)
        for lib in (source/'llama-vulkan').glob('*.so*'):
            if lib.is_file():copy('llama-vulkan/'+lib.name)
        for entry in json.loads((ROOT/'sources.json').read_text())['upscaler']['files']:
            file=ROOT/entry['file']
            if file.stat().st_size!=entry['size'] or sha(file)!=entry['sha256']:
                raise RuntimeError(f'Unexpected upstream file: {file}')
            copy(str(file.relative_to(source)))
        for rel in ('llama-vulkan/LICENSE','llama-vulkan/THIRD_PARTY_LICENSES.txt',
                    'upscayl-ncnn/LICENSE','upscayl-ncnn/CHAIN_LICENSES.txt'):
            copy(rel)
        for area in ('stable-diffusion.cpp','stable-diffusion.cpp/ggml'):
            directory=source/area
            notices=[]
            for file in sorted(directory.rglob('*')):
                if ('build' in file.relative_to(directory).parts or '.git' in file.parts):continue
                if file.is_file() and not file.is_symlink() and file.name.upper().startswith(('LICENSE','COPYING','NOTICE')) and file.stat().st_size<250000:
                    notices.append(str(file.relative_to(directory))+'\n\n'+file.read_text(errors='replace'))
            if not notices:raise RuntimeError(f'Missing licenses: {area}')
            (stage/area/'THIRD_PARTY_LICENSES.txt').parent.mkdir(parents=True,exist_ok=True)
            (stage/area/'THIRD_PARTY_LICENSES.txt').write_text('\n\n'.join(notices))
        copy('POPAI_LICENSE',ROOT/'LICENSE')
        elf_files=[]
        for file in sorted(stage.rglob('*')):
            if not file.is_file():continue
            with file.open('rb') as f:elf=f.read(4)==b'\x7fELF'
            if not elf:continue
            elf_files.append(file)
            # Keep the official upscaler byte-for-byte identical to its pinned asset.
            if file!=stage/'upscayl-ncnn/upscayl-bin':
                dynamic=subprocess.run(['readelf','-d',str(file)],capture_output=True,text=True,check=True).stdout
                if '(NEEDED)' in dynamic:
                    subprocess.run(['patchelf','--set-rpath','$ORIGIN',str(file)],check=True)
        # Set every library's search path before resolving transitive dependencies.
        for file in elf_files:
            linked=subprocess.run(['ldd',str(file)],capture_output=True,text=True)
            print(str(file.relative_to(stage)),linked.stdout,linked.stderr,flush=True)
            output=linked.stdout+linked.stderr
            if 'not found' in output or (linked.returncode and not any(text in output for text in ('not a dynamic executable','statically linked'))):
                raise RuntimeError(f'Missing or invalid library: {file}')
            # Reject accidental dependencies on the build tree.
            if str(ROOT) in linked.stdout or str(ROOT) in linked.stderr:raise RuntimeError(f'Non-relocatable dependency: {file}')
            symbols=subprocess.run(['readelf','--version-info',str(file)],capture_output=True,text=True,check=True).stdout
            versions=[tuple(map(int,m.split('.'))) for m in re.findall(r'\bGLIBC_(\d+\.\d+(?:\.\d+)?)\b',symbols)]
            if any(v>(2,39) for v in versions):raise RuntimeError(f'GLIBC above 2.39: {file}')
        manifest={'format':1,'platform':'linux-x86_64-v3','glibc_min':'2.39',
                  'source_sha256':{name:sha(ROOT/name) for name in ('sources.json','prompt-enhancer.json')},
                  'files':{str(f.relative_to(stage)):{'sha256':sha(f),'size':f.stat().st_size,'executable':bool(f.stat().st_mode&0o111)}
                           for f in sorted(stage.rglob('*')) if f.is_file()}}
        (stage/'bundle-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        archive=out/NAME
        with tarfile.open(archive,'w:gz',compresslevel=6) as f:
            f.add(stage,arcname='backends')
        record={'format':1,'archive':NAME,'size':archive.stat().st_size,'sha256':sha(archive),
                'platform':manifest['platform'],'glibc_min':manifest['glibc_min'],
                'manifest_sha256':sha(stage/'bundle-manifest.json'),
                'source_sha256':manifest['source_sha256']}
        (out/'backend-bundle.json').write_text(json.dumps(record,indent=2)+'\n')
        print(json.dumps(record,indent=2))
if __name__=='__main__':main()
