# popAI V27.11.26 — precompiled Vulkan backends

## Installation

Download the source archive from this release, extract it, and run
`./install.sh` as a normal user. Run `./start.sh` after installation.

The installer downloads a verified 145,516,568-byte (138.78 MiB) native
bundle containing seven executables, required engine libraries, Real-ESRGAN
weights and license notices. No CMake, compiler, Ninja, engine-source clone
or shader compilation is required on the user's computer. Pillow is installed
only from a binary wheel. The 4,482,402,656-byte prompt-enhancer model is
still downloaded separately; image models remain managed by the application.

An existing verified bundle is reused. Unknown or modified backend directories
are preserved, not overwritten. Model files, preferences and session storage
behavior remain unchanged from V25.11.26.

## Native package

- stable-diffusion.cpp: sd-cli and sd-server.
- llama.cpp: llama-server.
- Real-ESRGAN/NCNN: upscayl-bin and patched upscayl-chain.
- process-guard and vulkan-probe.
- Original pinned engine revisions and application patches.
- Archive and inner manifest SHA-256 verified; extraction rejects traversal,
  symlinks, duplicate entries, incomplete payloads and unexpected files.
- Build and installation workflows separated.

Linux x86-64-v3 (AVX2/FMA/BMI2 and other v3 features), glibc 2.39+,
Python 3.12+, and working Vulkan driver required. The build baseline is
Ubuntu 24.04; older glibc and CPUs below x86-64-v3 are not supported by
this bundle. No automatic fallback to local compilation.

## Validation

[Successful GitHub Actions build](https://github.com/usr-kmasx/popAI/actions/runs/45996229014)
from commit `e66c948a8aa45a8c1bb5fb808947f1d0dc40edda`.

- 47 backend, 6 download, 13 prompt-processing, 12 native installer, and
  26 frontend tests passed (104 total).
- Actual runtime installer accepted the native archive; 38 payload files
  verified. All seven executables and dynamic dependencies checked.
- On Arch Linux, sd-cli and llama-server version commands executed, native
  supervisor propagated successful and nonzero child exit codes, and
  Vulkan probe identified the AMD Radeon RX 580 2048SP (RADV POLARIS10).
- Both Real-ESRGAN executors generated a 256x256 PNG from a 64x64 PNG using
  Vulkan on that GPU.

Full language-model inference and image generation with the new native
bundle, a complete fresh install including the 4.48 GB model download,
and clean Debian/Ubuntu end-user installations have not been tested.
No generation settings, models, or image styles were changed.
