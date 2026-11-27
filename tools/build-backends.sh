#!/usr/bin/env bash
# Developer/CI build only: prepare and compile all pinned native engines.
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

say() { printf '\n[popAI] %s\n' "$*"; }
fail() { printf '\n[popAI] ERROR: %s\n' "$*" >&2; exit 1; }
trap 'printf "[popAI] Falha na linha %s. Arquivos de modelos e configurações foram preservados.\n" "$LINENO" >&2' ERR

expected_sha() {
  python3 - "$1" <<'PY'
import json,sys
src=json.load(open('sources.json',encoding='utf-8'))
key=sys.argv[1]
if key in src['tools']:
    record=src['tools'][key]
else:
    record=next((r for r in src['upscaler']['packages'] if r['url'].rsplit('/',1)[-1]==key),None)
if not record:raise SystemExit('Asset unknown: '+key)
print(record['sha256'])
PY
}
fetch_assets() {
  mkdir -p tools/downloads tools/local backends/upscayl-ncnn
  python3 - <<'PY'
from pathlib import Path
import sys,json,hashlib
sys.path.insert(0,'tools')
from fetch import fetch
src=json.load(open('sources.json',encoding='utf-8'))
assets=[]
if not Path('tools/cmake-4.5.0-linux-x86_64/bin/cmake').is_file():
    name='cmake-4.5.0-linux-x86_64.tar.gz'
    assets.append((name,src['tools'][name]))
if not Path('tools/local/Vulkan-Headers-1.4.363/include/vulkan/vulkan.h').is_file():
    name='vulkan-headers.tar.gz'
    assets.append((name,src['tools'][name]))
for part in src['upscaler']['packages']:
    name=part['url'].rsplit('/',1)[-1]
    if name.startswith('upscayl-bin-') and Path('backends/upscayl-ncnn/upscayl-bin').is_file():
        continue
    if name.startswith('realesrgan-') and all(Path(f).is_file() for f in (
         'backends/upscayl-ncnn/models/realesrgan-x4plus.bin',
         'backends/upscayl-ncnn/models/realesrgan-x4plus.param')):
        continue
    assets.append((name,part))
if not assets:print('[popAI] Ferramentas e arquivos base já disponíveis; sem novos downloads.',flush=True)
for filename,item in assets:
    path=Path('tools/downloads')/filename
    if path.is_file():
        with path.open('rb') as stream: actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=item['sha256']:
            raise SystemExit(f'Arquivo em cache com hash inesperado (preservado): {path}')
        print('[popAI] Cache verificado:',filename,flush=True)
    else:
        print('[popAI] Baixando:',filename,flush=True)
        fetch(item['url'],path,item['sha256'])
PY
}
prepare_tools() {
  local cmake=tools/cmake-4.5.0-linux-x86_64/bin/cmake
  if [[ ! -x "$cmake" ]]; then
    tar -xzf tools/downloads/cmake-4.5.0-linux-x86_64.tar.gz -C tools
  fi
  [[ -x "$cmake" ]] || fail "CMake local não foi extraído."
  "$cmake" --version | grep -q '4\.5\.0' || fail "A versão local do CMake não é a esperada."

  if [[ ! -f tools/local/Vulkan-Headers-1.4.363/include/vulkan/vulkan.h ]]; then
    tar -xzf tools/downloads/vulkan-headers.tar.gz -C tools/local
  fi
  [[ -f tools/local/Vulkan-Headers-1.4.363/include/vulkan/vulkan.h ]] || fail "Cabeçalhos Vulkan ausentes."
  local dir=tools/local/SPIRV-Headers-main
  local rev=5c6004e758e0c80185ef2cee93ae5c10fa342a5b
  if [[ -d "$dir/.git" ]]; then
    [[ "$(git -C "$dir" rev-parse HEAD)" == "$rev" ]] || fail "SPIRV-Headers existente em outra revisão; preservado: $dir"
  elif [[ -d "$dir" ]]; then
    # Older installations extracted the pinned SPIR-V archive without a .git dir.
    # Reuse valid headers; do not force a checkout over an existing directory.
    [[ -r "$dir/CMakeLists.txt" && -r "$dir/include/spirv/unified1/spirv.h" ]] || fail "SPIRV-Headers anterior incompleto; preservado: $dir"
    say "SPIRV-Headers legado encontrado; arquivos existentes preservados."
  else
    git init -q "$dir"
    git -C "$dir" remote add origin https://github.com/KhronosGroup/SPIRV-Headers.git
    git -C "$dir" fetch --depth 1 origin "$rev"
    git -C "$dir" checkout -q --detach FETCH_HEAD
  fi
}
prepare_upscaler() {
  local dir=backends/upscayl-ncnn
  if [[ ! -x "$dir/upscayl-bin" ]]; then
    unzip -oq -j tools/downloads/upscayl-bin-20240601-103425-linux.zip '*/upscayl-bin' '*/LICENSE' -d "$dir"
    chmod 755 "$dir/upscayl-bin"
  fi
  if [[ ! -f "$dir/models/realesrgan-x4plus.bin" || ! -f "$dir/models/realesrgan-x4plus.param" ]]; then
    unzip -oq tools/downloads/realesrgan-ncnn-vulkan-20220424-ubuntu.zip 'models/realesrgan-x4plus.*' -d "$dir"
  fi
  python3 - <<'PY'
import json,hashlib
from pathlib import Path
config=json.load(open('sources.json'))['upscaler']
for component in config['files']:
    file=Path(component['file'])
    if not file.is_file() or file.stat().st_size!=component['size']:
        raise SystemExit('Componente Real-ESRGAN ausente ou incompleto: '+str(file))
    with file.open('rb') as inp: digest=hashlib.file_digest(inp,'sha256').hexdigest()
    if digest!=component['sha256']:
        raise SystemExit('Componente Real-ESRGAN modificado, preservado: '+str(file))
    print('[popAI] Real-ESRGAN verificado:',file.name)
PY
}
prepare_backend() {
  local dir=backends/stable-diffusion.cpp
  local rev
  rev="$(python3 -c 'import json;print(json.load(open("sources.json"))["backend"]["revision"])')"
  if [[ -d "$dir/.git" ]]; then
    [[ "$(git -C "$dir" rev-parse HEAD)" == "$rev" ]] || fail "Motor existente em outra revisão; preservado: $dir"
  else
    [[ ! -e "$dir" ]] || fail "Pasta do motor existente sem Git; preservada: $dir"
    git init -q "$dir"
    git -C "$dir" remote add origin https://github.com/leejet/stable-diffusion.cpp.git
    git -C "$dir" fetch --depth 1 origin "$rev"
    git -C "$dir" checkout -q --detach FETCH_HEAD
  fi
  git -C "$dir" -c 'url.https://github.com/.insteadOf=git@github.com:' submodule update --init --depth 1 ggml
  local ggml_rev
  ggml_rev="$(python3 -c 'import json;print(json.load(open("sources.json"))["ggml"]["revision"])')"
  [[ "$(git -C "$dir/ggml" rev-parse HEAD)" == "$ggml_rev" ]] || fail "Submódulo ggml em revisão inesperada."

  # Confirm patches against pinned SHA-256 and apply once, without destroying edits.
  python3 - <<'PY'
import json,hashlib
from pathlib import Path
src=json.load(open('sources.json'))
for category in ('backend','ggml'):
    for item in src[category]['local_patches']:
        p=Path(item['file'])
        if hashlib.sha256(p.read_bytes()).hexdigest()!=item['sha256']:
            raise SystemExit('Patch alterado ou inválido (preservado): '+str(p))
PY
  local patchfile
  for patchfile in patches/esrgan-pixel-unshuffle.patch patches/private-resident-server.patch patches/esrgan-server-probe.patch; do
    if git -C "$dir" apply --reverse --check "$ROOT/$patchfile" >/dev/null 2>&1; then
      say "Patch já aplicado: $patchfile"
    elif git -C "$dir" apply --check "$ROOT/$patchfile" >/dev/null 2>&1; then
      git -C "$dir" apply "$ROOT/$patchfile"
    else
      fail "Não foi possível aplicar o patch sem sobrescrever alterações: $patchfile"
    fi
  done
}

[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || fail "Linux x86_64 required."
fetch_assets
prepare_tools
prepare_upscaler
prepare_backend
POPAI_STRICT_INSTALL=1 ./build.sh
python3 tools/setup-prompt-enhancer.py --backend-only
say "All native backends built. Run tools/package-backends.py to create the distribution."
