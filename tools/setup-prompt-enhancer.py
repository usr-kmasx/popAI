#!/usr/bin/env python3
"""Fetch and compile only project-local enhancer files; never installs packages."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from urllib.request import urlopen

from fetch import fetch

ROOT=Path(__file__).resolve().parents[1]


def verified(path,expected):
    if not path.exists():return False
    with path.open('rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
    if digest!=expected:raise ValueError(f'Arquivo existente diferente, preservado: {path}')
    return True


def main():
    config=json.loads((ROOT/'prompt-enhancer.json').read_text())
    model=config['model'];folder=ROOT/model['directory'];folder.mkdir(parents=True,exist_ok=True)
    target=folder/model['filename']
    if not verified(target,model['sha256']):fetch(model['url'],target,model['sha256'])
    if target.stat().st_size!=model['size']:raise ValueError('Tamanho incorreto do modelo.')
    with urlopen(model['license_url'],timeout=30) as response:(folder/'LICENSE').write_bytes(response.read())
    backend=config['backend'];destination=ROOT/backend['directory']
    cmake=ROOT/'tools/cmake-4.5.0-linux-x86_64/bin/cmake'
    if not cmake.is_file():raise RuntimeError('CMake local ausente. Prepare as ferramentas de compilação do projeto.')
    with tempfile.TemporaryDirectory(prefix='popai-llama-build-') as temporary:
        tmp=Path(temporary);archive=tmp/'source.tar.gz';fetch(backend['url'],archive,backend['sha256'])
        with tarfile.open(archive) as source:source.extractall(tmp,filter='data')
        source=next(p for p in tmp.iterdir() if p.is_dir() and p.name.startswith('llama.cpp-'))
        build=tmp/'build'
        flags=['-DCMAKE_BUILD_TYPE=Release','-DGGML_NATIVE=OFF','-DGGML_AVX2=ON',
               '-DGGML_AVX512=OFF','-DGGML_FMA=ON','-DGGML_F16C=ON','-DGGML_BACKEND_DL=OFF',
               '-DGGML_VULKAN=OFF','-DGGML_CUDA=OFF','-DGGML_BLAS=OFF','-DLLAMA_OPENSSL=OFF',
               '-DLLAMA_BUILD_TESTS=OFF','-DLLAMA_BUILD_EXAMPLES=OFF','-DLLAMA_BUILD_TOOLS=ON',
               '-DLLAMA_BUILD_SERVER=ON','-DLLAMA_BUILD_APP=OFF','-DLLAMA_BUILD_UI=OFF',
               '-DLLAMA_USE_PREBUILT_UI=OFF','-DCMAKE_BUILD_RPATH_USE_ORIGIN=ON',
               '-DCMAKE_BUILD_WITH_INSTALL_RPATH=ON','-DCMAKE_INSTALL_RPATH=$ORIGIN']
        subprocess.run([str(cmake),'-S',str(source),'-B',str(build),'-G','Ninja',*flags],check=True)
        subprocess.run([str(cmake),'--build',str(build),'--target','llama-server','--parallel',os.environ.get('BUILD_JOBS','4')],check=True)
        destination.mkdir(parents=True,exist_ok=True)
        for path in (build/'bin').iterdir():
            if path.name!='llama-server' and '.so' not in path.name:continue
            output=destination/path.name
            if path.is_symlink():output.unlink(missing_ok=True);output.symlink_to(path.readlink().name)
            elif path.is_file():
                staged=output.with_name('.'+output.name+'.new')
                shutil.copy2(path,staged)
                subprocess.run(['strip','--strip-unneeded',str(staged)],check=True)
                os.replace(staged,output)
        shutil.copy2(source/'LICENSE',destination/'LICENSE')
        notices=[]
        for area in ('vendor','ggml'):
            for path in sorted((source/area).rglob('*')):
                if path.is_file() and path.name.upper().startswith(('LICENSE','COPYING')) and path.stat().st_size<120000:
                    notices.append(str(path.relative_to(source))+'\n\n'+path.read_text(errors='replace'))
        (destination/'THIRD_PARTY_LICENSES.txt').write_text('\n\n'.join(notices))
    print('Melhorador pronto dentro do projeto. Inicie o app com ./start.sh.')


if __name__=='__main__':main()
