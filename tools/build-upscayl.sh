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
options=(-DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DNCNN_AVX512=OFF)
if [[ -f "$headers/vulkan/vulkan.h" ]]; then options+=("-DVulkan_INCLUDE_DIR=$headers"); fi
"$cmake" -S "$work/src/src" -B "$work/build" -G Ninja "${options[@]}"
"$cmake" --build "$work/build" --target upscayl-bin --parallel "${BUILD_JOBS:-4}"

mkdir -p -- "$runner_dir"
staging="$(mktemp "$runner_dir/.upscayl-chain.XXXXXXXX")"
install -s -m 755 "$work/build/upscayl-bin" "$staging"
help_text="$("$staging" -h 2>&1 || true)"
[[ "$help_text" == *"  -2 "* ]]
mv -f -- "$staging" "$runner_dir/upscayl-chain"
