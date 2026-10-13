# Popcorn SR — iteration 1

## Objective
Complete a standalone Docker NAS manager and paired or single-host Linux worker, with a guided Astryx interface, configurable scratch/output storage, and parity for DLSS neural rendering, DLSS Super Resolution, RTX Video Super Resolution, RTX Video HDR and DLSS frame generation. Publish verified milestones on clean main. All five NVIDIA stages are mandatory completion gates; the 0.2.0 preview is not full completion.

## Acceptance
- Authenticated one-use pairing, durable queue, worker leases, cancel/retry, streaming transfers.
- Original library read-only; independently validated output, collision-safe publishing.
- CPU encode and conventional enhancement tested on actual media end to end.
- NVIDIA codecs and enhancement stages enabled by real processing checks only. All five stages must have usable controls, previews and compatible combinations; see [parity requirements](docs/nvidia-parity.md).
- NAS, worker, single-host and NVIDIA Docker examples with ARM64/AMD64 builds.
- Browser desktop/mobile flows and error states verified.
- CI tests, Docker smoke, public commits on main as thekozugroup@gmail.com.

## Evidence and limits
Version 0.1.1 software implementation is complete, including the ARM64 AI encoding fix. Public repository: https://github.com/thekozugroup/Popcorn-SR. All development commits use main and thekozugroup@gmail.com, with no AI co-author tags.

Verified on 2026-10-12:
- Nine automated tests, including timestamp-preserving frame piping and encoder-failure reporting. The media/API coverage includes: real encode/upload/download, checksums, source changes, lease exclusivity, cancel/retry, revoked workers, incompatible codecs, traversal, HDR and 16-bit SDR rejection, subtitle/attachment/chapter preservation, scratch identity changes, preview-to-full guards.
- Two Chromium workflows: actual five-second preview and full six-second video on a CPU worker, retained device/output/settings, authenticated download, login errors, pairing and keyboard navigation. Axe reported zero violations and no horizontal overflow in tested 390/768/1440 light/dark library/processing views.
- Linux ARM64 paired Docker containers: generated source → download → 2× resize/noise reduction → upload → validated output. Original checksum unchanged, audio preserved, scratch job files removed. Receipt and UI captures are under gitignored `evidence/`.
- NVIDIA codecs are absent on this CPU host, as expected; capability discovery genuinely encoded with CPU H.264/HEVC/AV1 instead of inferring support from a codec list.
- Official RealESRGAN_x4plus checkpoint SHA-256 verified, strictly loaded network and tiled inference. Physical DGX Spark (Ubuntu 24.04 ARM64, GB10, driver 580.173.02) passed H.264/HEVC/AV1 NVENC checks and two-computer source → processing → return roundtrips for resizing and Real-ESRGAN CUDA + H.264 NVENC. Generated two-second 160×96 SDR+audio clips produced validated 320×192 output with matching transfer hashes and unchanged originals. A localhost SSH reverse tunnel connected the Mac manager and Spark worker; this is not a NAS/LAN throughput benchmark. The worker used an existing vLLM CUDA PyTorch image and temporary PyAV dependencies, not the optional AI Dockerfile.
- NGC PyTorch 26.09-py3 registry manifest includes Linux AMD64 and ARM64. The larger optional AI image was not built or executed on a GPU here.
- Ruff, Tailwind build and npm high-severity dependency audit pass. GitHub verification includes Linux AMD64 Docker processing; the release workflow verifies its exact tagged commit before publishing both architectures.
- The independent Impeccable review scored preview-first setup, direct full-video continuation and queue action hierarchy resolved. Its named roles were unavailable, so fresh general agents used the shipped role instructions. Design context reported legacy PRODUCT.md headings; the established brief is preserved rather than migrated as a side effect.

All Spark test files, model/dependency copies, temporary caches and container instances were held in RAM and removed afterward; existing images and running services were preserved. ARM64 PyAV lacked NVENC, so the AI adapters now stream timestamped raw frames through an in-memory NUT pipe to system FFmpeg.

Physical RTX 5080 encode/inference, the optional AI image, representative library quality, long jobs, HDR preservation, external-drive hot-unplug and NAS/network throughput remain acceptance gates. Native Linux DLSS rendering is not implemented; an experimental external engine contract is supplied. Transfers restart from the beginning after interruption.

## Next device acceptance
1. Validate the optional AI image and RTX 5080, using scratch on the intended mounted external drive.
2. Compare representative SDR clips for quality, temporal artifacts and throughput; NVIDIA VFX/DLSS need separate compatible runtimes.
3. Test Unraid delivery, Optane scratch writes, cancellation, network interruption and mount/service dependencies before a whole-library run.

## Research
- DGX Spark has 1 NVENC / 1 NVDEC; ARM64 compatibility must be checked per SDK/runtime.
- fast-rtxvsr is MIT wrapper code with separately licensed NVIDIA runtimes; Windows requirements.
- Merserk Visual Enhancer is Windows/D3D12, source-available proprietary; reference and separately installed CLI only.
- Ordinary host USB-C ports do not provide a standard host-to-host network. Use Ethernet or an OS-supported bridge adapter.

## Iteration 2 — Astryx Web UI

Migrated the workspace to official Astryx 0.6.8 components on React 19, with a compiled Neutral extension preserving zinc surfaces, blue-500 actions, system fonts and 44px targets. Vite emits local static assets; the NAS still needs no Node server. Preserved one-use pairing, saved recipes, preview/full continuation, queue actions and capability-based choices. Worker enhancement labels now show every verified engine, including Real-ESRGAN.

Current local evidence: both Chromium workflows pass real preview/full processing, 390/768/1440 light/dark accessibility and overflow checks, heartbeat edit retention, mobile drawer navigation, zero JavaScript/CSP violations, and 44px activation targets. Ten Python tests pass, including manager availability when the UI build is missing. The selector’s fixed runtime stylesheet is permitted by its exact build-generated hash; arbitrary inline code remains blocked. A built wheel includes UI assets and policy. The built ARM64 container passed a real paired source → encode → return roundtrip with complete UI assets and security policy. The independent reviewer scored all three material fixes resolved: tablet/control readability, complete path wrapping, and manager availability without generated UI. DESIGN.md and its sidecar record the Astryx system. Public release publication runs only after the exact tagged source passes CI; see the repository’s Actions and Releases for that status.

Public 0.1.1 was anonymously pulled and passed a paired ARM64 Docker roundtrip. Its release includes the physical Spark and publication verification receipts. This iteration changes the UI and packaging; hardware limits above remain.

## Completion goal — iteration 3

User requested full completion on 2026-10-12. Goal active. Expanded at the user's request to feature parity with the five main NVIDIA video enhancements in [Visual Enhancer](https://github.com/Merserk/dlss5-visual-enhancer):

1. DLSS neural rendering, including its video controls and temporal settings.
2. DLSS super resolution, including DLAA, Quality, Balanced, Performance and Ultra Performance modes.
3. RTX video super resolution, including quality and sizing controls.
4. RTX Video HDR conversion, with real 10-bit HDR output and color/metadata validation.
5. DLSS frame generation, with genuine DLSSG processing and target-FPS validation.

These must be usable stages, with previews and compatible combinations, not labels or substitutions using conventional FFmpeg filters. Completion requires executable implementation and honest real-engine evidence for supported platform/hardware combinations. Architecture or licensing constraints must be documented as unresolved requirements until a supported backend is available. Core software and the Astryx 0.2.0 preview are published; deployment/failure recovery and NVIDIA feature parity remain active work.

Acceptance for this iteration:
- Reproducible, pinned Linux AMD64/ARM64 CUDA AI worker packaging, with a physical Spark render using the packaged runtime.
- Real Unraid manager → Spark worker → Unraid output across the LAN. Preserve existing services and remove owned test containers/images/files; all Spark job/model/cache/state data stays in RAM during acceptance.
- Scratch filesystem identity persists across worker restarts; missing/replaced drives fail closed. Graceful worker shutdown terminates processing and removes job files. Safe recovery handles only files owned by Popcorn SR.
- Failure tests cover cancellation, disconnection, restart and scratch replacement; single-host CPU and GPU contracts remain supported.
- Unraid instructions work without Compose, which is absent on the user's NAS.
- Final software checks, tagged publication and public-image verification; clean pushed main using the requested identity.

User supplied `atlas` for NAS acceptance and explicitly deferred the RTX 5080 desktop. No external Optane mount is currently visible on Spark. Physical Optane acceptance and representative library image-quality approval require the actual drive/media; filesystem-loss tests can still be performed. Native Linux DLSS/VFX support is constrained by separately licensed compatible runtimes and architecture availability; unavailable engines remain disabled. Windows remains future work per the user's scope, but Windows-only reference implementation behavior informs the five-feature parity requirements above. Deferring desktop acceptance does not waive any of the five feature requirements.

### Current iteration progress

- Expanded the completion requirements to all five requested NVIDIA stages; no conventional substitute or external-template-only implementation can close those gates.
- Pinned Linux AMD64/ARM64 PyTorch 2.13.0 + CUDA 13.0, PyAV and NumPy in uv.lock. The optional AI image built locally and imported its locked CUDA runtime; GPU execution of this exact package is still pending.
- Added persisted scratch filesystem identity, private atomic markers/state, inherited active-job locks, scoped restart recovery and graceful process-group shutdown. Eight new tests cover replacement, old marker migration, unknown-folder preservation, inherited child locks, real FFmpeg cancellation and capability timeout descendants and real AI-encoder lock inheritance and immediate cancellation while failure reporting is stalled. Processing stops before the worker waits for a disconnected manager. Eighteen tests and Ruff pass locally.
- Spark NGX initialization, capability discovery and a small Super Resolution feature creation passed with NVIDIA ARM64 SDK 310.9.1. A static-frame CUDA pixel evaluation also passed after using a writable CUDA surface for output: all 196,608 channel values were finite. This proves native SDK execution, not decoded-video/temporal quality or a production adapter. Video Super Resolution and Frame Generation were unavailable through this CUDA query; other APIs remain to investigate. All owned probe artifacts were in RAM and removed.
- Next: integrate native SR video decoding, temporal inputs and encoding; investigate native Vulkan DLSSG and compatible neural/HDR runtimes; finish packaged GPU and Unraid delivery acceptance. Desktop and physical Optane checks remain deferred/unavailable as recorded above.

User reinforced NAS preservation: isolate test resources, keep temporary files in RAM, avoid changes to existing services or data, remove only owned test resources, and verify cleanup. Do not prune shared Docker caches or erase ordinary system/audit logs.

Cleanup verification: read-only NAS inspection found the same 15 existing service names and no Popcorn test folder in /dev/shm. No NAS container, image or file was created during this iteration. Spark inspection found the same four existing service names and no owned NGX probe folder remaining in /dev/shm; no Docker image/container was created there.

Final local checks for this milestone: 18 Python tests, Ruff, frozen-lock validation, UI production build, zero npm vulnerabilities, both Chromium workflows, default Docker build and an actual ARM64 paired Docker processing/return roundtrip passed. The Docker result was 320×192 with audio, matching transfer checksums, unchanged original and cleaned scratch. The optional AI image also rebuilt successfully with the final worker source; physical execution of this exact package remains pending.

### Native DLSS video milestone

- Implemented an independent MIT CUDA/NGX bridge and optional pinned PyAV/NumPy/OpenCV video adapter. Actual NVIDIA Super Resolution renders every frame; estimated backward motion, cut/time-gap resets and finite-pixel validation guard the experimental SDR path. No fallback renderer. NGX permits one session per process lifetime in this adapter because real shutdown/recreation tests exposed initialization failures and a crash; settings verification uses isolated subprocesses.
- Physical Spark tests passed 48-frame, two-second 192×128 → 384×256 DLSS videos in H.264, H.265/HEVC and AV1. All frame timestamps matched exactly. A 38-frame VFR clip retained exact timestamps. NVENC B-frame reordering is disabled for timestamped AI output after the tested encoder shifted/duplicated PTS with it enabled. The exact-matching tests passed after this change. These are generated clips, not representative image-quality or throughput benchmarks.
- All 25 SR mode/preset-hint pairs (DLAA/Quality/Balanced/Performance/Ultra Performance × Default/J/K/L/M) and all three motion-estimation settings passed real three-frame NGX evaluation/readback checks. The full settings check took about 264 seconds on this Spark with other services running; startup budgets are bounded and cancellation still kills the process group. Presets are NVIDIA hints, not proof of which internal model the runtime chose.
- Added mode sizing and backward-compatible old recipes, worker/manager compatibility checks for advanced settings, Astryx controls showing only verified combinations, and saved queue summaries of mode/preset/motion. H.265 / HEVC naming is now consistent. Browser fixtures are labeled UI-only and do not count as GPU proof.
- Added a 320 MB locally built ARM64 NGX worker image with locked dependencies, plus paired/single-host Compose overlay and separate read-only runtime/driver mounts. Its build/import passed; physical GPU execution of this exact image and native manager-to-worker return remain pending. NVIDIA binaries/headers are not bundled in source or the image. The public 0.2.0 image is unchanged.
- Added six tests for actual optical-flow direction across three quality levels, cut/gap resets, recipe sizing, verified settings/claim routing and private cache cleanup. Twenty-four Python tests, Ruff, lock validation, production UI build, zero npm vulnerabilities and three browser workflows pass. Default ARM64 Docker paired processing/return passed with intact sources, audio and cleaned scratch. DLSS UI checks include 1440 light/390 dark Axe/overflow and preserved selection after state refresh.
- The fresh Impeccable reviewer scored both scoped fixes resolved: saved DLSS preset/motion in queue rows and consistent H.265 / HEVC naming. Its `ship` verdict covers those two fixes. Named role dispatch was unavailable, so fresh general agents used the shipped reviewer/documenter role instructions. The documenter preserved the existing design system; it reported prior radii/status/sidecar drift without changing it as part of this ordinary extension.
- Added Unraid installation instructions that do not require Compose. No NAS files, containers or images were created during this milestone. Spark used only uniquely owned RAM test folders and temporary containers from an already present image; dependencies, native bridge, SDK copies, driver caches and generated clips were removed. Before/after running-service and image inventories matched.
- Remaining: exact NGX package acceptance and paired return, representative SR quality/color/long-job checks, native Vulkan DLSSG, compatible RTX VSR/HDR and neural-rendering runtimes, stage combinations, actual NAS delivery and available external-drive acceptance. Full completion goal remains active; no other stage is waived by SR passing.

### Dedicated NGX package acceptance

- The exact ARM64 NGX worker built from `3be022b7620c2c6fccbb88cb42768e93f82c94dd` passed physical Spark startup and paired delivery. Import verification compared immutable filesystem layers, architecture and environment: Docker's archive/config conversion produced different daemon image IDs, so raw IDs were not treated as equivalent evidence. All 25 SR mode/preset pairs were verified at startup in 288.74 seconds.
- A Mac manager paired through a localhost SSH reverse tunnel and received three five-second generated SDR previews: H.264/Performance/Default/high motion at 320×192, HEVC/Quality/K/medium at 240×144 and AV1/DLAA/J/low at 160×96. Each retained audio, passed authenticated-download checksum validation and preserved the original checksum. Job scratch was clean afterward. Receipt: gitignored `evidence/ngx-packaged-spark.json`.
- The test removed its dedicated Docker image/container and uniquely owned RAM folder. Before/after existing-service and image inventories matched. No NAS resources were created. This establishes dedicated packaged GPU processing and paired return, not NAS delivery, LAN throughput, external-drive behavior or representative library quality.
- Exact-source CI passed: https://github.com/thekozugroup/Popcorn-SR/actions/runs/38335664383 (24 Python tests, Ruff, production UI/dependency checks, three browser workflows, default paired Docker smoke and NGX Docker build/import). The published 0.2.0 image remains unchanged.
- Next: native Vulkan DLSSG and compatible RTX VSR/HDR/neural runtimes, stage combinations, quality/color/long-job checks and NAS/external-drive acceptance. The five-stage completion goal remains active.

### Vulkan Frame Generation capability milestone

- Added an independent MIT headless Vulkan diagnostic linked to the operator-provisioned NVIDIA SDK's typed static wrapper. It checks extensions, the actual NVIDIA device, feature requirements, initialization and capabilities. `fg --create` additionally creates a 256×192 RGBA8 DLSSG feature and submits/waits for its initialization commands. Failed requirement queries produce null support flags, rather than interpreting untouched zeros as support. This does not evaluate images or enable a worker engine.
- Physical Spark GB10, driver 580.173.02 and SDK 310.9.1 passed Vulkan extension discovery, Frame Generation requirements (supported), NGX initialization, availability/initialization values, actual DLSSG feature creation and command submission. The earlier CUDA result was API-specific. Pixel evaluation and timing remain unverified; `video_render_verified` stays false.
- Used an existing temporary container with matched host Vulkan loader/driver libraries mounted read-only. SDK/header/static-wrapper copies, compiled executable, shader/driver caches and scratch were in uniquely owned RAM storage; all were removed with the container. Existing-service and image inventories matched. No image was created and the NAS remained untouched. Receipt: gitignored `evidence/vulkan-spark.txt`.
- Next: Vulkan DLSSG pixel evaluation and timestamped video integration, then real controls/preview delivery; RTX VSR/HDR/neural backends, combinations and other acceptance gates remain active. No native capability or feature-creation result substitutes for producing frames.

### Vulkan DLSSG generated-pixel milestone

- Added independent MIT Vulkan image/staging-buffer/fence resources and an optional DLSSG pixel diagnostic. `fg --render` requires a build with `POPCORN_VULKAN_SMOKE` and separately provisioned NVIDIA helper/parameter headers. It uploads three 256×192 RGBA8 frames with flat float depth and backward pixel motion, seeds the output on the GPU, and reads both image pixels and NVIDIA's disable-interpolation buffer after a bounded fence wait.
- Physical Spark evaluation passed all three frames. All 49,152 seeded pixels were replaced per frame. The reset frame exactly copied the input and reported interpolation disabled. Both moving frames reported interpolation enabled and output different from both adjacent inputs. This is genuine synthetic DLSSG pixel production, not a decoded-video or cadence result. `pixel_render_verified` is true and `video_render_verified` remains false. Receipt: gitignored `evidence/vulkan-pixels-spark.txt`.
- The test used an existing image, matched host Vulkan/graphics libraries mounted read-only, and private RAM folders for SDK/header/static-wrapper copies, compiler temporary files, executable and driver/shader caches. It removed its container and RAM files; existing service/image inventories matched. No new image or NAS resource was created.
- Commit `5d65a5e` passed exact-source CI: https://github.com/thekozugroup/Popcorn-SR/actions/runs/38338162299. Next: turn verified DLSSG pixels into a timestamped video backend, then expose verified settings and pair delivery. Remaining NVIDIA stages and all other acceptance gates remain active.

### Native Vulkan DLSSG video milestone

- Added an independent MIT C ABI over the separately provisioned NVIDIA Vulkan SDK wrapper, plus an optional pinned Python video adapter. Intermediate frames come from actual DLSSG evaluation with backward pixel motion, flat depth and reset-on-cut/gap history. Each process owns one native NGX session. The SDK's disable-interpolation decision is checked per pair and retained across later multi-frame indices; poisoning it again per index caused a real 4× failure, which was corrected before the passing tests.
- Physical Spark GB10, driver 580.173.02 and SDK 310.9.1 passed 48→96-frame, two-second 192×128 SDR videos in H.264/high motion, H.265/HEVC/medium and AV1/low. Native 3×–6× produced 144/192/240/288 frames; a 38-frame VFR clip produced 76. Every output fully decoded. Timestamp error was at most 0.5 ms and duration error at most 1 ms, within Matroska precision. The actual runtime reported five generated frames per pair, permitting a maximum 6× multiplier. These tiny generated clips are execution/cadence evidence, not HD throughput or representative quality. Receipt: gitignored `evidence/native-dlssg-video-spark.txt`.
- Spark testing used an existing image with the matched host loader/graphics libraries mounted read-only. Native compilation, dependencies, SDK/header/static-wrapper copies, source/output clips and shader/driver caches stayed in uniquely owned RAM storage. All owned test resources were removed; running-service and image inventories matched. No NAS resource was created.
- Added three timing/cache failure tests, and CI compile checks for both Vulkan sources using explicitly obtained, pinned temporary NVIDIA/Khronos headers. Headers are removed afterward; no SDK binary is downloaded by CI or bundled in source/images. The NGX image now installs the Vulkan loader and import-checks both native video adapters. Its local ARM64 build/import passed; this is not physical graphics-driver package acceptance.
- Final local checks passed: 27 Python tests, Ruff, lock validation, both native Vulkan syntax checks, production UI build, default Docker build, actual paired ARM64 Docker processing/return with audio/checksums/intact source, and NGX Docker build/import. Commit `74a73c8` passed exact-source CI: https://github.com/thekozugroup/Popcorn-SR/actions/runs/38339195908.
- The new CLI writes a video-only intermediate and rejects non-8-bit-SDR, anamorphic or odd-dimension sources. It has no worker/UI integration yet. Next: verified worker controls and media return, arbitrary target FPS/cascade modes, exact NGX graphics packaging, then compatible combinations and remaining RTX VSR/HDR/neural stages. The full five-stage goal remains active. Published 0.2.0 is unchanged.
