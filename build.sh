#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CMAKE="$ROOT/tools/cmake-4.5.0-linux-x86_64/bin/cmake"
PREFIX="$ROOT/tools/local/prefix"
"$CMAKE" -S "$ROOT/tools/local/SPIRV-Headers-main" -B "$ROOT/tools/local/spirv-build" -G Ninja \
  -DSPIRV_HEADERS_ENABLE_TESTS=OFF -DCMAKE_INSTALL_PREFIX="$PREFIX"
"$CMAKE" --install "$ROOT/tools/local/spirv-build"
"$CMAKE" -S "$ROOT/backends/stable-diffusion.cpp" -B "$ROOT/backends/stable-diffusion.cpp/build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DSD_VULKAN=ON -DSD_WEBP=OFF -DSD_WEBM=OFF \
  -DSD_SERVER_BUILD_FRONTEND=OFF -DCMAKE_PREFIX_PATH="$PREFIX" \
  -DCMAKE_CXX_FLAGS="-isystem $PREFIX/include" \
  -DVulkan_INCLUDE_DIR="$ROOT/tools/local/Vulkan-Headers-1.4.363/include"
"$CMAKE" --build "$ROOT/backends/stable-diffusion.cpp/build" --target sd-cli sd-server --parallel "${BUILD_JOBS:-4}"
"$ROOT/backends/stable-diffusion.cpp/build/bin/sd-cli" --version

"${CXX:-c++}" -O2 "$ROOT/native/process-guard.cpp" -o "$ROOT/backends/process-guard.new"
mv "$ROOT/backends/process-guard.new" "$ROOT/backends/process-guard"
"${CXX:-c++}" -O2 -I"$ROOT/tools/local/Vulkan-Headers-1.4.363/include" "$ROOT/native/vulkan-probe.cpp" -lvulkan -o "$ROOT/backends/vulkan-probe.new"
mv "$ROOT/backends/vulkan-probe.new" "$ROOT/backends/vulkan-probe"

upscaler="$ROOT/backends/upscayl-ncnn"
if [[ -x "$upscaler/upscayl-bin" && ( ! -x "$upscaler/upscayl-chain" || "$ROOT/patches/upscayl-two-pass.patch" -nt "$upscaler/upscayl-chain" ) ]]; then
  if ! "$ROOT/tools/build-upscayl.sh"; then
    echo 'A compilação da variante de duas passagens falhou. O executor original continua disponível.' >&2
  fi
fi
