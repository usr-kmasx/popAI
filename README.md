# popAI

**Current release: 22.11.26** · [Release notes](docs/release-22.11.26.md) · [Previous release](docs/release-21-1.11.26.md)

Generate, edit, and upscale wallpapers locally on Linux. popAI runs image models
on Vulkan and exports PNGs up to 4K UHD at 16:9. It serves its interface in your
browser and runs inference on your computer.

## Features

- Text-to-image generation with Z-Image Turbo, FLUX.2 Klein 4B, and FLUX 3
  Image Klein. Both Klein models support editing with up to 10 reference images.
- Real-ESRGAN upscaling through NCNN and Vulkan. Choose the base generation
  size, aspect ratio, and final resolution separately.
- Model management with folder import, resumable downloads, and SHA-256 checks
  against the published manifest.
- Live progress and previews. The total includes preparation, generation,
  upscaling, and PNG finalization. The clock shows an estimate for the current
  stage when progress data is available.
- On-demand Vulkan prompt enhancement with **Simple**, **More details**,
  **Creative**, and **Cinematic Art** modes, plus undo and cancellation. The
  model is unloaded from GPU memory after each enhancement.
- Built-in 4:3 sketch editor for Klein reference images: freehand strokes, text,
  rectangles, ellipses, straight lines, and arrows; selection, resizing,
  undo/redo, and re-editing from the reference thumbnail.
- Click uploaded reference thumbnails to inspect them in a larger preview.
  Hide the prompt manually to view a generated image without the input overlay.

## Getting started

This is a source release for x86-64 Linux. You need a Vulkan-capable GPU with a
working driver, Python 3.12 or newer with Pillow, and enough disk space for the
models you choose. Building the engines requires Git, a C/C++ toolchain, Ninja,
`patch`, `unzip`, `glslc`, and the Vulkan loader and development libraries. The optional
direct PNG writer also uses libpng development headers.

Clone the release and open the project folder.

```bash
git clone --branch 22.11.26 https://github.com/usr-kmasx/popAI.git
cd popAI
```

Follow [Build the image engines](#build-the-image-engines) on a fresh clone.
With the engines ready and Pillow available, start the app.

```bash
./start.sh
```

Open [popAI on your computer](http://127.0.0.1:7860/). To use a different
port, run `./start.sh --port 7861`. Press **Ctrl+C** in the terminal to stop
the server and release its engines.

In **Settings → Models**, choose a download folder and download one model set,
or use **Find existing models** to import compatible files in place. Each set
uses a generator, text encoder, and VAE. Download sizes are approximately
**9.4 GB** for Z-Image Turbo, **7.1 GB** for FLUX.2 Klein 4B, and **9.0 GB** for
FLUX 3 Image Klein. To add a model directory at launch, pass
`--model-dir /path/to/models`.

## Using popAI

1. Choose a profile in **Settings → Stable Diffusion** and select a size,
   aspect ratio, and output resolution in **Resolution**.
2. Enter a prompt and press **Enter**, or use the arrow button beside **New** and **Hide**.
   With a Klein profile, use **+** to attach reference images, or the pen beside
   it to sketch a reference. Z-Image Turbo does not accept reference images.
3. Optionally enhance a description with the magic-wand menu. **Undo** (the
   last option) restores the prior wording when available. The **Cinematic Art**
   enhancer uses the local Qwen3.5-4B HauhauCS Aggressive Q8_0 with sampling
   temperature `0.3` and a scene-fidelity prompt. Each enhancement sends a
   separate request without conversation history; improving, undoing, and improving again reuses the
   original text, not a previous conversation.
4. When the final PNG appears, drag to pan, use the mouse wheel to zoom, or
   double-click to reset the view. Click the download arrow to save the PNG
   at its full resolution.

| Model | Default steps | Faster presets | Reference editing |
| --- | ---: | --- | --- |
| Z-Image Turbo | 9 | 4 or 5 steps | Text only |
| FLUX.2 Klein 4B | 4 | 2 or 3 steps | Supported |
| FLUX 3 Image Klein | 16 | 5 or 8 steps | Supported |

The generation engine stays loaded between requests. Automatic weight placement
can use system RAM when GPU memory is limited. The generator produces a base
image, which the upscaler enlarges to fit the exact output dimensions.

The prompt is saved in the browser. Reloading the page draws a new seed and
restores the current result and reference images while the server is running.
Use **New** below the prompt field to draw a new seed and clear the current
result while keeping the prompt and references. Generating again without **New**
reuses the page seed even if the text changes. The **Hide** button sits beside
**Generate** and **New**; it hides the prompt without clearing it. Hovering or
clicking the status message below the input restores the prompt. The gear opens
settings on click and has no hide menu on hover. There is no automatic
five-second hide timer.

With a Klein model selected, the pen immediately to the right of **+** opens
the built-in **4:3** sketch editor (960 × 720 pixels). It includes a brush,
eraser, text, selection/movement, four resizable shapes (rectangle, ellipse,
straight line, arrow), a color palette, stroke-size slider and undo/redo.
Confirming attaches a PNG reference. This editor currently uses a fixed 4:3
canvas, even when the output wallpaper aspect ratio differs.

Click a reference thumbnail to reopen a sketch for editing or enlarge a regular
uploaded image. Reconfirming a sketch replaces its existing reference without
changing its order. Editable items survive F5 in the same browser tab while
session data is available. Sketches created before this state was stored can
only be reopened as a flattened PNG background, with new objects added on top.
The older standalone editor at `prototypes/sketch.html` is a design prototype;
the integrated editor lives in `web/sketch.html`, `web/sketch.css`, and
`web/sketch.js`.

Click Download for a permanent copy of a generated image. The server removes
temporary images when it shuts down.

## Build the image engines

Run these commands from the root of a fresh checkout. The build places the
engines and downloaded tools inside the project. If Pillow is missing, you
can use a project-local virtual environment.

```bash
python3 -m venv tools/local/venv
source tools/local/venv/bin/activate
python -m pip install Pillow
```

Download the pinned CMake and Vulkan headers, the NCNN executor, and the
Real-ESRGAN weights. The downloader verifies the archives against
[`sources.json`](sources.json).

```bash
python3 - <<'PY'
import json
from pathlib import Path
import sys

sys.path.insert(0, "tools")
from fetch import fetch

sources = json.loads(Path("sources.json").read_text())
downloads = Path("tools/downloads")
for name in ("cmake-4.5.0-linux-x86_64.tar.gz", "vulkan-headers.tar.gz"):
    asset = sources["tools"][name]
    fetch(asset["url"], downloads / name, asset["sha256"])
for asset in sources["upscaler"]["packages"]:
    name = asset["url"].rsplit("/", 1)[-1]
    fetch(asset["url"], downloads / name, asset["sha256"])
PY

mkdir -p tools/local backends/upscayl-ncnn
tar -xzf tools/downloads/cmake-4.5.0-linux-x86_64.tar.gz -C tools
tar -xzf tools/downloads/vulkan-headers.tar.gz -C tools/local

spirv=tools/local/SPIRV-Headers-main
git init "$spirv"
git -C "$spirv" fetch --depth 1 https://github.com/KhronosGroup/SPIRV-Headers.git 5c6004e758e0c80185ef2cee93ae5c10fa342a5b
git -C "$spirv" checkout --detach FETCH_HEAD

upscaler=backends/upscayl-ncnn
unzip -j tools/downloads/upscayl-bin-20240601-103425-linux.zip '*/upscayl-bin' '*/LICENSE' -d "$upscaler"
chmod +x "$upscaler/upscayl-bin"
unzip tools/downloads/realesrgan-ncnn-vulkan-20220424-ubuntu.zip 'models/realesrgan-x4plus.*' -d "$upscaler"
```

Check out the stable-diffusion.cpp revision, initialize its ggml submodule,
apply the popAI patches, then build.

```bash
backend=backends/stable-diffusion.cpp
git init "$backend"
git -C "$backend" fetch --depth 1 https://github.com/leejet/stable-diffusion.cpp.git 532d2c15c430a785a712b2d94281f04e733008a4
git -C "$backend" checkout --detach FETCH_HEAD
git -C "$backend" submodule update --init --depth 1 ggml

git -C "$backend" apply "$PWD/patches/esrgan-pixel-unshuffle.patch"
git -C "$backend" apply "$PWD/patches/private-resident-server.patch"
git -C "$backend" apply "$PWD/patches/esrgan-server-probe.patch"

./build.sh
```

`./build.sh` also attempts to build the optional NCNN runner for chained
upscaling and direct PNG output. Set `BUILD_JOBS` to control compilation
parallelism. If you created a virtual environment, activate it again before
running `./start.sh` in a new terminal.

## Optional prompt enhancer

Run `python3 tools/setup-prompt-enhancer.py` after preparing the local build
tools. It downloads the pinned Qwen3.5-4B HauhauCS Aggressive GGUF Q8_0 model
(about 4.48 GB) and builds a dedicated Vulkan llama.cpp server inside the project.
The enhancer does **not** preload at application startup: it starts on the
each **Enhance** request and its process exits after completion, cancellation,
connection loss or failure to free its VRAM. Vulkan-capable hardware, `glslc`,
and the local Vulkan/SPIR-V headers under `tools/local` are required. This
configuration intentionally does not fall back silently to CPU. The previous
LFM3 and Huihui Q4 model weights are not included or required.
[Prompt enhancer manifest](prompt-enhancer.json)

## Tests

The backend and browser logic tests run without generating images on the GPU.
The optional headless Chromium sketch tests and their isolated test-server
instructions are described in the [21.11.26 release notes](docs/release-21.11.26.md),
with the current Vulkan enhancer and Qwen Q8_0 updates in the
[22.11.26 release notes](docs/release-22.11.26.md).

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
node --test tests/frontend.test.cjs
```

## License

The popAI source is licensed under the [MIT License](LICENSE).
The engines and model weights have their own licenses. See the
[engine sources](sources.json), [image model downloads](model-downloads.json),
and [prompt model license](models/prompt-enhancer/LICENSE) for upstream details.
