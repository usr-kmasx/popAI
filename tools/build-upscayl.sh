#!/usr/bin/env bash
# Build the optional two-pass runner beside the original, using its pinned sources.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
revision=22774bc42e2bc3c785b5b585d213d960b1348ad5
work="$(mktemp -d)"
runner_dir="$root/backends/upscayl-ncnn"
staging=""
cleanup() {
    rm -rf -- "$work"
    if [[ -n "$staging" ]]; then rm -f -- "$staging"; fi
}
trap cleanup EXIT

git init -q "$work/src"
git -C "$work/src" remote add origin https://github.com/upscayl/upscayl-ncnn.git
git -C "$work/src" fetch -q --depth 1 origin "$revision"
git -C "$work/src" checkout -q --detach "$revision"
git -C "$work/src" -c 'url.https://github.com/.insteadOf=git@github.com:' \
    submodule update --init --recursive --depth 1 --jobs "${BUILD_JOBS:-4}"
git -C "$work/src" apply "$root/patches/upscayl-two-pass.patch"
git -C "$work/src" apply "$root/patches/upscayl-final-png.patch"

cmake="$root/tools/cmake-4.5.0-linux-x86_64/bin/cmake"
if [[ ! -x "$cmake" ]]; then cmake=cmake; fi
headers="$root/tools/local/Vulkan-Headers-1.4.363/include"
options=(-DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DNCNN_AVX512=OFF -DNCNN_RUNTIME_CPU=ON -DCMAKE_C_FLAGS=-march=x86-64-v3 -DCMAKE_CXX_FLAGS=-march=x86-64-v3)
if [[ -f "$headers/vulkan/vulkan.h" ]]; then options+=("-DVulkan_INCLUDE_DIR=$headers"); fi
"$cmake" -S "$work/src/src" -B "$work/build" -G Ninja "${options[@]}"
"$cmake" --build "$work/build" --target upscayl-bin --parallel "${BUILD_JOBS:-4}"

mkdir -p -- "$runner_dir"
staging="$(mktemp "$runner_dir/.upscayl-chain.XXXXXXXX")"
install -s -m 755 "$work/build/upscayl-bin" "$staging"
help_text="$("$staging" -h 2>&1 || true)"
[[ "$help_text" == *"  -2 "* ]]
mv -f -- "$staging" "$runner_dir/upscayl-chain"
python3 - "$work/src" "$runner_dir/CHAIN_LICENSES.txt" <<'LICENSES'
from pathlib import Path
import sys
source=Path(sys.argv[1])
notices=[]
for path in sorted(source.rglob('*')):
    if path.is_file() and not path.is_symlink() and path.name.upper().startswith(('LICENSE','COPYING','NOTICE')) and path.stat().st_size<250000:
        notices.append(str(path.relative_to(source))+'\n\n'+path.read_text(errors='replace'))
if not notices:raise SystemExit('Missing upscayl/NCNN license notices')
Path(sys.argv[2]).write_text('\n\n'.join(notices))
LICENSES
