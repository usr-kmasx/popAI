#!/usr/bin/env bash
# Runtime installer only. Native engines are built by the separate CI workflow.
set -Eeuo pipefail
export PYTHONDONTWRITEBYTECODE=1
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
say() { printf '\n[popAI] %s\n' "$*"; }
fail() { printf '\n[popAI] ERROR: %s\n' "$*" >&2; exit 1; }
trap 'printf "[popAI] Falha na linha %s. Arquivos de modelos e configurações foram preservados.\n" "$LINENO" >&2' ERR
usage() {
  cat <<'HELP'
Uso: ./install.sh [--check | --bundle ARQUIVO]

Sem opções: instala os backends Vulkan pré-compilados, dependências de execução,
            Pillow (wheel) e o modelo do melhorador de prompts.
            Não compila código nem baixa modelos de imagem da aba Models.
--check:    verifica a instalação sem modificar arquivos.
--bundle:   instala uma cópia local do mesmo pacote de backends verificado.

Linux x86_64-v3 (AVX2/FMA/BMI2), glibc >= 2.39, Python >= 3.12.
Execute como usuário normal.
HELP
}
CHECK_ONLY=0
BUNDLE=()
case "${1:-}" in
  "") [[ $# -eq 0 ]] || { usage; exit 2; };;
  --check) [[ $# -eq 1 ]] || { usage; exit 2; }; CHECK_ONLY=1 ;;
  --bundle) [[ $# -eq 2 ]] || { usage; exit 2; }; BUNDLE=(--archive "$(realpath "$2")") ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac
[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || fail "Requer Linux x86_64."
[[ "$EUID" -ne 0 ]] || fail "Execute ./install.sh sem sudo."
libc="$(getconf GNU_LIBC_VERSION 2>/dev/null || true)"
[[ "$libc" == glibc\ * ]] || fail "Requer glibc >= 2.39."
version="${libc#glibc }"
[[ "$(printf '%s\n' 2.39 "$version" | sort -V | head -n 1)" == 2.39 ]] || fail "Requer glibc >= 2.39 (Ubuntu 24.04 ou equivalente)."
flags="$(grep -m1 '^flags[[:space:]]*:' /proc/cpuinfo || true)"
for flag in avx avx2 bmi1 bmi2 fma f16c movbe popcnt cx16 lahf_lm ssse3 sse4_1 sse4_2 xsave; do
  [[ " $flags " == *" $flag "* ]] || fail "CPU sem suporte x86-64-v3 ($flag)."
done
[[ " $flags " == *" abm "* || " $flags " == *" lzcnt "* ]] || fail "CPU sem suporte LZCNT."
[[ -f backend-bundle.json ]] || fail "Este checkout ainda não possui um pacote pré-compilado publicado e verificado."
python_ok() {
  command -v python3 >/dev/null && python3 -c 'import sys,venv,ensurepip; sys.exit(sys.version_info < (3,12))' >/dev/null 2>&1
}
system_ok() {
  python_ok || return 1
  command -v vulkaninfo >/dev/null && command -v ldd >/dev/null || return 1
  local cache
  cache="$(ldconfig -p 2>/dev/null || /sbin/ldconfig -p 2>/dev/null)" || return 1
  for lib in libvulkan.so.1 libpng16.so.16 libstdc++.so.6 libgomp.so.1; do
    grep -F "$lib " <<< "$cache" | grep 'x86-64' >/dev/null || return 1
  done
}
install_packages() {
  local distro=""
  if [[ -r /etc/os-release ]]; then
    . /etc/os-release
    distro="${ID:-}"
    case " ${ID_LIKE:-} " in
      *" arch "*) distro=arch ;;
      *" debian "*) distro=debian ;;
    esac
  fi
  command -v sudo >/dev/null || fail "Instale as dependências de execução ou sudo."
  case "$distro" in
    arch|cachyos|endeavouros)
      say "Instalando somente dependências de execução via pacman."
      sudo pacman -S --needed --noconfirm python vulkan-icd-loader vulkan-tools libpng gcc-libs ca-certificates
      ;;
    debian|ubuntu|linuxmint|pop)
      say "Instalando somente dependências de execução via apt."
      sudo apt-get update
      sudo apt-get install -y python3 python3-venv ca-certificates libvulkan1 vulkan-tools libpng16-16t64 libstdc++6 libgcc-s1 libgomp1
      ;;
    *) fail "Instale Python 3.12+, venv, Vulkan, libpng, libstdc++ e libgomp para a distribuição '$distro'." ;;
  esac
}
check_vulkan() {
  vulkaninfo --summary >/dev/null 2>&1 || fail "Vulkan não detectado. Configure o driver da GPU e repita."
}
prepare_python() {
  local python=tools/local/venv/bin/python
  [[ -x "$python" ]] || python3 -m venv tools/local/venv
  if ! "$python" -c 'from PIL import Image' >/dev/null 2>&1; then
    say "Instalando Pillow a partir de wheel, sem compilação."
    "$python" -m pip install --only-binary=:all: --disable-pip-version-check --no-cache-dir 'Pillow>=11,<13'
  fi
  "$python" -c 'from PIL import Image; import sys; assert sys.version_info >= (3,12)'
}
check_install() {
  python3 tools/install-backends.py --check
  local python=tools/local/venv/bin/python
  [[ -x "$python" ]] || fail "Ambiente Python ausente."
  "$python" -c 'from PIL import Image; import sys; assert sys.version_info >= (3,12)'
  local binary linked
  for binary in backends/stable-diffusion.cpp/build/bin/sd-cli backends/stable-diffusion.cpp/build/bin/sd-server backends/upscayl-ncnn/upscayl-bin backends/upscayl-ncnn/upscayl-chain backends/llama-vulkan/llama-server backends/process-guard backends/vulkan-probe; do
    [[ -x "$binary" ]] || fail "Faltando executável: $binary"
    linked="$(ldd "$binary" 2>&1)" || { [[ "$linked" == *"not a dynamic executable"* || "$linked" == *"statically linked"* ]] || fail "$linked"; }
    [[ "$linked" != *"not found"* ]] || fail "Biblioteca dinâmica ausente em $binary: $linked"
  done
  backends/stable-diffusion.cpp/build/bin/sd-cli --version
  backends/llama-vulkan/llama-server --version
  local help_text
  help_text="$(backends/upscayl-ncnn/upscayl-chain -h 2>&1 || true)"
  [[ "$help_text" == *"  -2 "* && "$help_text" == *"  -P "* ]] || fail "Ampliador avançado incompatível."
  "$python" - <<'PY'
import json,hashlib
from pathlib import Path
assert set(json.load(open('model-downloads.json')))=={'z-image-turbo','klein','qwen-image21-experimental'}
model=json.load(open('prompt-enhancer.json'))['model']
path=Path(model['directory'])/model['filename']
assert path.is_file() and path.stat().st_size==model['size'], 'Modelo do melhorador ausente.'
with path.open('rb') as inp: assert hashlib.file_digest(inp,'sha256').hexdigest()==model['sha256'], 'Hash do melhorador inválido.'
print('[popAI] Melhorador de prompts e todos os backends verificados.')
PY
  say "Motores e dependências locais estão prontos. Execute ./start.sh."
}
if (( CHECK_ONLY )); then
  say "Verificação somente leitura."
  system_ok || fail "Dependências de execução ausentes."
  check_vulkan
  check_install
  exit 0
fi
say "Instalando popAI com backends pré-compilados. Nenhum compilador será executado."
if ! system_ok; then install_packages; fi
system_ok || fail "Dependências de execução ainda ausentes."
check_vulkan
python3 tools/install-backends.py "${BUNDLE[@]}"
prepare_python
say "Baixando/verificando o modelo do melhorador de prompts."
tools/local/venv/bin/python tools/setup-prompt-enhancer.py --model-only
check_install
say "Instalação concluída. Abra ./start.sh e escolha os modelos em Settings → Models."
