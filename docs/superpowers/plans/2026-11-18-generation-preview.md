# Blurred generation preview

**Goal:** Show the completed base as a strongly blurred, animated preview during upscaling, replacing it with the validated final PNG.

**Design:** Reuse the existing temporary base through a current-job-only PNG endpoint. A separate browser layer keeps blur active throughout loading and prevents an unblurred base from flashing. Animate a light reconstruction sweep using CSS; respect reduced motion. The existing successful-job cleanup deletes the base. The preview has no download action and does not change generation or upscaling settings.

**Decisions:** The preview begins after base generation because no intermediate base exists during sampling. Keep the existing image until the preview is decoded. Restore it on cancellation/failure; prevent late preview loads from replacing the final image. Keep retry intermediates on failure, as already supported.

- [x] Expose only the current validated base during upscaling/finalizing; preserve existing cleanup.
- [x] Add the blurred preview layer, reconstruction sweep, and race-safe transitions.
- [x] Run existing backend/frontend suites and transient lifecycle/race checks without creating new test scripts or generating images with the models.

**Validation:** 18 backend and 6 frontend tests pass. Transient fixture checks cover the no-store preview endpoint, unrelated IDs/traversal rejection, base deletion after success, unavailable preview after cancellation, late preview after success/error/both cancel actions, failed final decoding preserving the prior image, retry, stale status after cancellation, and late final decoding after a new submit. Visually checked the real CSS in an isolated local instance using an existing image; stopped the temporary server afterward. No generation or upscaling parameters changed.
