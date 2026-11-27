# Precompiled Vulkan backends

The end-user installer and developer build are separate.

## Runtime installation

Run `./install.sh` from a published source checkout containing
`backend-bundle.json`. This tracked file pins the release URL, compressed size,
archive SHA-256, inner manifest SHA-256 and the source configuration fingerprints.
A checkout without a verified package record fails explicitly instead of
falling back to compilation or using an unverified executable.

The archive contains exactly the required native executables and shared libraries,
upstream Real-ESRGAN x4plus weights, and license notices. It excludes the llama
model, image model weights, source trees, build tools, and local configurations.

| Component | Executable |
|---|---|
| stable-diffusion.cpp | sd-cli, sd-server |
| llama.cpp | llama-server |
| Real-ESRGAN / NCNN | upscayl-bin, upscayl-chain |
| Native helpers | process-guard, vulkan-probe |

All previous revisions and patch hashes remain pinned. The native package is
built for Linux x86-64-v3, with a glibc 2.39 baseline (Ubuntu 24.04).
CPU instructions are limited to the declared baseline; Vulkan remains the
GPU backend. Older glibc or CPUs without the required features are rejected
before download. The host still supplies its own Vulkan loader/driver and
standard runtime libraries. The Python environment requires Python 3.12+ and
a binary Pillow wheel; pip cannot build Pillow from source.

The installer verifies the complete archive before extraction, validates a
strict file manifest and rejects traversal, duplicates, links and unexpected
payloads. It extracts to a private staging directory and renames that directory
only after validation. Existing unrecognized backend folders and user model
files are preserved. A verified bundle is reused. The temporary download is
deleted after successful installation. Downloaded model files are separate.

## Developer build

The GitHub Actions workflow builds on Ubuntu 24.04 with the pinned source
revisions and patches. It runs `tools/build-backends.sh`, then
`python3 tools/package-backends.py`. It downloads no 4.48 GB enhancer weights.
The same commands are available to developers who prepare all build
dependencies in a compatible Ubuntu 24.04 environment. They are never
called by the normal installer.

The packager collects required libraries with relative runtime search paths,
checks the glibc symbol baseline and missing dependencies, preserves the
official upscaler bytes, and emits the archive plus a checksum record in
`dist/`. The workflow extracts the artifact into a different directory,
checks the seven executables and tests native command-line entrypoints.

After a successful build, the tested archive must be published to a versioned
GitHub release, and its archive and manifest checksums must be pinned in the
source checkout. Do not publish an application release with missing bundle
metadata. Cross-distribution and actual Vulkan smoke tests must be documented
separately; a CI runner without a hardware GPU cannot validate real inference.
