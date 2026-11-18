# Temporary FLUX 3 Image Klein profile

Add a separate `flux3-klein` test profile (Q8 generator, Qwen3-VL 4B Q4_K_M encoder, existing FLUX.2 VAE). Keep both existing profiles and the current selection. Default to 16 steps, Euler, CFG 1, discrete scheduler as documented by the bundled engine. Reuse Vulkan/offload/mmap/reference/upscaling and lifecycle logic. Label the profile as temporary in the selector and model library. No system installation, new inference framework or image generation for verification.

- [x] Download pinned weights to the existing SSD model root; verify sizes/hashes and retain license/source records.
- [x] Identify new components by metadata/tensors, expose compatible slots and add the temporary preset without changing existing defaults.
- [x] Validate actual components and native load-only path; run existing checks, preserving user generation testing and current settings.

Validation: native sd-server loaded all three actual components successfully on RX 580 Vulkan with mmap/RAM offload, then was stopped; no images generated. Log: `logs/flux3-load-only.log`; summary: `logs/flux3-test-profile-20261118.json`. Both new downloads passed pinned SHA-256 and size checks; shared VAE hash matches the official package. Existing backend suite: 18 passed; frontend: 6 passed. Transient selector check verified distinct defaults and compatible component filtering for all three profiles. Current saved settings were unchanged by load-only validation.
