# popAI

**Current release: V24-1.11.26** · [Release notes](docs/release-24-1.11.26.md) · [Previous release](docs/release-24.11.26.md)

Generate, edit, and upscale wallpapers locally on Linux. popAI runs image models
on Vulkan and exports PNGs up to 4K UHD at 16:9. It serves its interface in your
browser and runs inference on your computer.

## Features

- Text-to-image generation with Z-Image Turbo, FLUX.2 Klein 4B, and
  Qwen Image 2.1 (ChatR Labs Turbo, Q8). Klein and Qwen support editing
  with up to 10 reference images.
- Real-ESRGAN upscaling through NCNN and Vulkan. Choose the base generation
  size, aspect ratio, and final resolution separately.
- Model management with three named download folders, reuse of imported models,
  resumable downloads, and SHA-256 checks against the published manifest.
- Live progress and previews. The total includes preparation, generation,
  upscaling, and PNG finalization. The clock shows an estimate for the current
  stage when progress data is available.
- On-demand Vulkan prompt enhancement with **Simple**, **More details**,
  **Creative**, and **Dramatic** modes, plus undo and cancellation. The
  model is unloaded from GPU memory after each enhancement. A first-pass corrector
  interprets and translates the description before the selected enhancer runs.
- Animated mascot with pointer tracking, idle expressions, blinking, live model
  output, and progress-dependent motion during image generation.
- Built-in 4:3 sketch editor for Klein and Qwen reference images: freehand strokes, text,
  rectangles, ellipses, straight lines, and arrows; selection, resizing,
  undo/redo, and re-editing from the reference thumbnail.
- Integrated 2D pose editor with articulated joints, searchable presets, camera
  pan and zoom, and movable, proportionally resizable pose objects in sketches.
  Reference-specific generation instructions distinguish poses and sketches from
  imported images. No additional model or dependency is required.
- Click uploaded reference thumbnails to inspect them in a larger preview.
  Hide the prompt manually to view a generated image without the input overlay.

## Getting started

The popAI installer prepares the Linux x86-64 runtime, Vulkan image-generation
engine, Real-ESRGAN upscaler, and on-demand prompt enhancer with **one command**.
It works on Arch Linux, Debian and Ubuntu with a Vulkan-capable GPU and a
working GPU driver. It installs missing system build packages with sudo only
when needed; all compiled application binaries and Python packages stay under
the popAI project. Internet access and free disk space are required.

Clone the current repository and run the installer **as your normal user**:

```bash
git clone https://github.com/usr-kmasx/popAI.git
cd popAI
./install.sh
```

The installer fetches pinned build tools, verifies download hashes, builds the
local Vulkan engines and upscaler, installs Pillow in a private Python virtual
environment, and downloads/builds the prompt enhancer (including its 4.48 GB
local Qwen model). It deletes only the disposable build-download archives
after successful verification. It does **not** delete your saved projects,
configurations, images or image-model weights.

When installation finishes, launch the app:

```bash
./start.sh
```

Open [popAI on your computer](http://127.0.0.1:7860/). To use a different
port, run `./start.sh --port 7861`. Press **Ctrl+C** in the launch terminal
to stop the application. The installer does not start the server itself.

**Image model weights are not downloaded during installation.** On first
launch the app opens **Settings → Models**. Choose a folder, then download only
the model(s) you want, or import compatible weights already on disk.
The three model sets are **Z-Image Turbo**, **FLUX.2 Klein 4B**, and
**Qwen Image 2.1 · ChatR Labs Turbo**.

To verify a completed installation without downloading or modifying anything:

```bash
./install.sh --check
```

Rerun `./install.sh` to repair/rebuild missing parts. It reuses existing
verified files and never downloads image-model weights. Hardware-specific GPU
drivers and an accessible Vulkan device remain prerequisites; an incompatible
GPU or unavailable upstream download cannot be fixed automatically.

## Using popAI

1. Choose one of the three models in **Settings → Stable Diffusion**. Click a
   model to expand its generation presets and select one. Manual changes to
   sampling settings activate **Custom settings** while keeping that model.
   Choose a size, aspect ratio, and output resolution in **Resolution**.
2. Enter a prompt and press **Enter**, or use the arrow button beside **New** and **Hide**.
   With a Klein or Qwen profile, use **+** to attach reference images, or the pen beside
   it to sketch a reference. Inside the pencil editor, open the pose tool to
   select a preset or adjust the joints, then choose **Use in sketch**. Move and
   resize the pose within your composition before confirming the sketch.
   Z-Image Turbo does not accept reference images.
3. Optionally enhance a description with the magic-wand menu. **Undo** (the
   last option) restores the prior wording when available. The **Dramatic**
   enhancer uses the local Qwen3.5-4B HauhauCS Aggressive Q8_0 with sampling
   temperature `0.3` and a specific dark semi-realistic anime wallpaper art-direction prompt.
   All four modes first run a private corrector (`prompt-corrector.txt`) that
   interprets the original description, resolves ambiguity without artistic additions,
   and translates it into en-US while preserving requested literal image text.
   The selected enhancer then receives only the corrected English paragraph.
   Both independent completion requests use the same loaded Vulkan model,
   with a 512-token reasoning budget for the corrector and 192 for the enhancer,
   without conversation history.
   The local mascot displays the model-emitted reasoning and answer for each stage
   in a separate minimizable panel. The panel opens on the first text delta,
   preserves each completed response for three seconds, and can be minimized into
   the active eye. Neither replaces the input during processing.
   The input changes only after both stages succeed; canceling or failing
   preserves the original, and Undo restores the wording before enhancement.
4. When the final PNG appears, drag to pan, use the mouse wheel to zoom, or
   double-click to reset the view. Click the download arrow to save the PNG
   at its full resolution. The mascot moves from the center to the corner during
   image generation, settles as measured progress advances, and stays there until
   New clears the image. On the empty home screen prompt enhancement stays centered;
   idle eyes follow the pointer, change expression, and blink occasionally.

| Model | Default steps | Faster presets | Reference editing |
| --- | ---: | --- | --- |
| Z-Image Turbo | 9 | 4 or 5 steps | Text only |
| FLUX.2 Klein 4B | 4 | 3 steps | Supported |
| Qwen Image 2.1 · ChatR Labs Turbo | 8 | 4 steps (Fast; same LoRA) | Supported |

All three models use the same resident `sd-server` engine by default, keeping their
weights loaded between generations. Qwen applies its Turbo LoRA through the server's
structured LoRA request; the `sd-cli` path remains available when persistence is disabled.
Qwen reference images are copied into temporary, size-limited PNGs aligned to multiples
of 32, preserving the uploaded originals.
Automatic weight placement can use system RAM when GPU memory is limited. The generator produces a base
image, which the upscaler enlarges to fit the exact output dimensions. The NCNN upscaler
loads its Real-ESRGAN weights from the original model files when needed, using the Linux
filesystem page cache when available. It releases its Vulkan resources after each job.

The prompt is saved in the browser. Reloading the page draws a new seed and
restores the current result and reference images while the server is running.
Use **New** below the prompt field to draw a new seed and clear the current
result while keeping the prompt and references. Generating again without **New**
reuses the page seed even if the text changes. The **Hide** button sits beside
**Generate** and **New**; it hides the prompt without clearing it. Hovering or
clicking the status message below the input restores the prompt. The gear opens
settings on click and has no hide menu on hover. There is no automatic
five-second hide timer.

With a Klein or Qwen model selected, the pen immediately to the right of **+** opens
the built-in **4:3** sketch editor (960 × 720 pixels). It includes a brush,
eraser, text, selection/movement, four resizable shapes (rectangle, ellipse,
straight line, arrow), a color palette, stroke-size slider and undo/redo.
Confirming attaches a PNG reference. This editor currently uses a fixed 4:3
canvas, even when the output wallpaper aspect ratio differs.

### Pose references

Open the pose tool inside the sketch editor. Choose a searchable preset or
manipulate the joints, adjust rotations and body-part thickness, mirror the
pose, and reorder or hide layers. Hold **Space** and drag, or drag with the
middle mouse button, to pan the camera. Scroll to zoom around the cursor;
click the zoom percentage to reset the view.

**Use in sketch** inserts a transparent PNG as a selectable object. Move,
resize proportionally, or delete it; undo/redo and multiple pose objects are
supported. The original drawing tools remain available. The sketch retains
editable object positions when reopened, but the inserted pose is rasterized:
its individual joints cannot be re-articulated inside the sketch. Pose
projects can be saved and opened separately as JSON in the pose editor.

Only the completed sketch is sent as a reference. When generating, popAI
adds guidance to the outgoing prompt for each numbered editor reference:
pose sketches guide posture and composition; ordinary sketches guide layout.
Images imported with **+** receive no automatic guidance. The visible input
remains unchanged. This is prompt-based guidance, not guaranteed pose locking;
results depend on the image model and the requested scene. No new AI model
or additional inference is used to create poses.


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

## Installation and development notes

`./install.sh` replaces the previous manual multi-command build procedure.
It prepares the pinned dependencies defined in
[`sources.json`](sources.json) and
[`prompt-enhancer.json`](prompt-enhancer.json), applies the project patches,
and invokes `./build.sh` and `tools/setup-prompt-enhancer.py` as needed.
These are internal build helpers, **not** additional commands that a new user
must run.

The model browser uses [`model-downloads.json`](model-downloads.json) for its
independently verified image-model downloads. Presets reuse each model's
weights. Source revisions, manifests, patches and license notices are kept so
future reinstallations remain reproducible. Disposable downloaded ZIP/tar
archives are discarded after successful installation; native build sources and
binaries remain locally for repair and incremental compilation.

On systems with an unsupported distribution or a missing Vulkan driver,
the script reports the prerequisite instead of claiming a successful setup.
The supported installer targets are Arch Linux, Debian and Ubuntu on x86-64.

## Tests

The backend and browser logic tests run without generating images on the GPU.
The optional headless Chromium sketch tests and their isolated test-server
instructions are described in the [21.11.26 release notes](docs/release-21.11.26.md).
Qwen Image 2.1, grouped presets, model library changes and compatibility
checks are documented in the [22-1.11.26 release notes](docs/release-22-1.11.26.md).
The two-stage prompt workflow and animated mascot are documented in the
[24.11.26 release notes](docs/release-24.11.26.md). The integrated pose editor
is documented in the [24-1.11.26 release notes](docs/release-24-1.11.26.md).

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
node --test tests/frontend.test.cjs tests/eyes.test.cjs
```

## License

The popAI source is licensed under the [MIT License](LICENSE).
The engines and model weights have their own licenses. See the
[engine sources](sources.json), [image model downloads](model-downloads.json),
and [prompt model license](models/prompt-enhancer/LICENSE) for upstream details.
