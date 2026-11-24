#!/usr/bin/env bash
# Install all project-local engines, their toolchain, and the prompt enhancer.
# Image generation model weights are intentionally installed later from the UI.
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

say() { printf '\n[popAI] %s\n' "$*"; }
fail() { printf '\n[popAI] ERROR: %s\n' "$*" >&2; exit 1; }
trap 'printf "[popAI] Falha na linha %s. Arquivos de modelos e configurações foram preservados.\n" "$LINENO" >&2' ERR

usage() {
  cat <<'HELP'
Uso: ./install.sh [--check]

Sem opções: instala dependências, motores e melhorador de prompts.
            Não baixa os modelos de imagem da aba Models.
--check:    verifica a instalação sem modificar arquivos ou executar servidores.

Execute como usuário normal. O instalador só solicita sudo quando faltam
dependências do sistema. Suporte a Arch Linux, Debian e Ubuntu (Linux x86_64).
HELP
}
CHECK_ONLY=0
case "${1:-}" in
  "") ;;
  --check) CHECK_ONLY=1 ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { usage >&2; exit 2; }
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || fail "Requer Linux x86_64."
[[ "$EUID" -ne 0 ]] || fail "Execute ./install.sh sem sudo; a elevação será solicitada somente quando necessária."

python_ok() {
  command -v python3 >/dev/null && python3 -c 'import sys, venv, ensurepip; sys.exit(sys.version_info < (3,12))' >/dev/null 2>&1
}
system_ok() {
  local tool
  for tool in git python3 ninja gcc g++ patch unzip tar glslc strip pkg-config curl vulkaninfo; do
    command -v "$tool" >/dev/null 2>&1 || return 1
  done
  python_ok || return 1
  pkg-config --exists libpng vulkan || return 1
  # grep -q may make ldconfig receive SIGPIPE under pipefail; consume all output.
  if command -v ldconfig >/dev/null 2>&1; then
    ldconfig -p 2>/dev/null | grep 'libvulkan.so.1' >/dev/null || return 1
  elif [[ -x /sbin/ldconfig ]]; then
    /sbin/ldconfig -p 2>/dev/null | grep 'libvulkan.so.1' >/dev/null || return 1
  else
    return 1
  fi
  return 0
}
install_packages() {
  local distro=""
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    distro="${ID:-}"
    case " ${ID_LIKE:-} " in
      *" arch "*) distro="arch" ;;
      *" debian "*) distro="debian" ;;
    esac
  fi
  local -a elevation=()
  if command -v sudo >/dev/null; then elevation=(sudo)
  else fail "Instale sudo e execute novamente para instalar as dependências ausentes."
  fi
  case "$distro" in
    arch|cachyos|endeavouros)
      say "Instalando dependências de compilação e Vulkan via pacman."
      "${elevation[@]}" pacman -S --needed --noconfirm base-devel git python python-pip ninja shaderc pkgconf patch unzip curl ca-certificates vulkan-icd-loader vulkan-tools libpng vulkan-headers
      ;;
    debian|ubuntu|linuxmint|pop)
      say "Instalando dependências de compilação e Vulkan via apt."
      "${elevation[@]}" apt-get update
      "${elevation[@]}" apt-get install -y build-essential git python3 python3-venv python3-pip ninja-build glslc pkg-config patch unzip curl ca-certificates libvulkan1 libvulkan-dev vulkan-tools libpng-dev libomp-dev
      ;;
    *) fail "Distribuição '$distro' sem suporte a instalação automática de pacotes. Suportadas: Arch, Debian e Ubuntu." ;;
  esac
}
check_vulkan() {
  command -v vulkaninfo >/dev/null 2>&1 || fail "Instale vulkan-tools e o driver Vulkan da sua GPU."
  vulkaninfo --summary >/dev/null 2>&1 || fail "Vulkan não detectado. Configure o driver da GPU (RADV/Intel/NVIDIA) e repita a instalação."
}
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
prepare_python() {
  local python=tools/local/venv/bin/python
  if [[ ! -x "$python" ]]; then
    python3 -m venv tools/local/venv
  fi
  if ! "$python" -c 'from PIL import Image' >/dev/null 2>&1; then
    say "Instalando Pillow no ambiente Python privado."
    "$python" -m pip install --disable-pip-version-check --no-cache-dir 'Pillow>=11,<13'
  fi
  "$python" -c 'from PIL import Image; import sys; assert sys.version_info >= (3,12)'
}
check_install() {
  local python=tools/local/venv/bin/python
  local bin
  for bin in "$python" \
      backends/stable-diffusion.cpp/build/bin/sd-cli \
      backends/stable-diffusion.cpp/build/bin/sd-server \
      backends/upscayl-ncnn/upscayl-bin \
      backends/upscayl-ncnn/upscayl-chain \
      backends/process-guard backends/vulkan-probe \
      backends/llama-vulkan/llama-server; do
    [[ -x "$bin" ]] || fail "Faltando executável: $bin"
  done
  "$python" -c 'from PIL import Image'
  local help_text
  help_text="$(backends/upscayl-ncnn/upscayl-chain -h 2>&1 || true)"
  [[ "$help_text" == *"  -2 "* && "$help_text" == *"  -P "* ]] || fail "Ampliador avançado sem suporte a duas passagens/PNG direto."
  python3 - <<'PY'
import json,hashlib
from pathlib import Path
m=json.load(open('model-downloads.json'))
assert set(m)=={'z-image-turbo','klein','qwen-image21-experimental'}, 'Catálogo de modelos de imagem inesperado.'
conf=json.load(open('prompt-enhancer.json'))['model']
model=Path(conf['directory'])/conf['filename']
assert model.is_file() and model.stat().st_size==conf['size'], 'Modelo do melhorador de prompts ausente.'
with model.open('rb') as inp: assert hashlib.file_digest(inp,'sha256').hexdigest()==conf['sha256'], 'Hash do melhorador inválido.'
for entry in json.load(open('sources.json'))['upscaler']['files']:
    file=Path(entry['file'])
    assert file.is_file() and file.stat().st_size==entry['size'],str(file)
print('[popAI] 3 famílias de imagem configuradas. Pesos de imagem serão baixados pelo app.')
print('[popAI] Melhorador de prompts e ampliador verificados.')
PY
  local binary
  for binary in backends/stable-diffusion.cpp/build/bin/sd-cli backends/stable-diffusion.cpp/build/bin/sd-server backends/upscayl-ncnn/upscayl-bin backends/upscayl-ncnn/upscayl-chain backends/llama-vulkan/llama-server; do
    if command -v ldd >/dev/null && ldd "$binary" 2>/dev/null | grep -q 'not found'; then
      fail "Biblioteca dinâmica ausente em $binary"
    fi
  done
  say "Motores e dependências locais estão prontos. Execute ./start.sh."
}
cleanup_downloads() {
  # Delete only checked, disposable installation archives, not user data or model files.
  local name
  for name in cmake-4.5.0-linux-x86_64.tar.gz vulkan-headers.tar.gz \
      upscayl-bin-20240601-103425-linux.zip realesrgan-ncnn-vulkan-20220424-ubuntu.zip \
      spirv-headers.tar.gz; do
    local path="tools/downloads/$name"
    [[ -f "$path" && ! -L "$path" ]] || continue
    local sha actual
    sha="$(expected_sha "$name")"
    actual="$(sha256sum "$path" | cut -d' ' -f1)"
    if [[ "$sha" == "$actual" ]]; then rm -- "$path"; fi
  done
  rmdir tools/downloads 2>/dev/null || true
}
if (( CHECK_ONLY )); then
  say "Verificação somente leitura."
  system_ok || fail "Alguma ferramenta ou biblioteca do sistema está ausente."
  check_vulkan
  check_install
  exit 0
fi
say "Instalador completo do popAI. Os pesos Z-Image, FLUX.2 e Qwen ficam para a interface."
if ! system_ok; then install_packages; fi
system_ok || fail "As dependências necessárias ainda não estão disponíveis."
check_vulkan
prepare_python
say "Baixando/verificando ferramentas e pesos do ampliador."
fetch_assets
prepare_tools
prepare_upscaler
say "Preparando o motor de inferência."
prepare_backend
say "Compilando os motores locais (sem iniciar servidores)."
POPAI_STRICT_INSTALL=1 ./build.sh
say "Preparando o melhorador de prompts."
# The dedicated setup script checks the model hash and compiles the pinned llama.cpp.
# Skip its expensive rebuild if both its files already exist and are healthy.
if [[ -x backends/llama-vulkan/llama-server ]] && \
    python3 - <<'PY'
import json,hashlib,sys
from pathlib import Path
conf=json.load(open('prompt-enhancer.json'))['model']; p=Path(conf['directory'])/conf['filename']
if not p.is_file() or p.stat().st_size!=conf['size']:sys.exit(1)
with p.open('rb') as f: sys.exit(hashlib.file_digest(f,'sha256').hexdigest()!=conf['sha256'])
PY
then
  say "Melhorador já instalado e íntegro; compilação dispensada."
else
  tools/local/venv/bin/python tools/setup-prompt-enhancer.py
fi
check_install
cleanup_downloads
say "Instalação concluída. Abra ./start.sh e escolha os modelos em Settings → Models."
