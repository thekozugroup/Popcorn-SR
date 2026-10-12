# Popcorn SR — iteration 1

## Objective
Ship a usable standalone Docker manager and paired worker, with a guided web interface, single-host mode, configurable external scratch storage, Linux NVIDIA/AI adapters, optional Windows RTX/DLSS CLI adapters, and a public repository with clean main history.

## Acceptance
- Authenticated one-use pairing, durable queue, worker leases, cancel/retry, streaming transfers.
- Original library read-only; independently validated output, collision-safe publishing.
- CPU encode and conventional enhancement tested on actual media end to end.
- NVIDIA codecs and optional AI engines enabled by runtime smoke checks only.
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

Current local evidence: both Chromium workflows pass real preview/full processing, 390/768/1440 light/dark accessibility and overflow checks, heartbeat edit retention, mobile drawer navigation, zero JavaScript/CSP violations, and 44px activation targets. Nine Python tests pass. The selector’s fixed runtime stylesheet is permitted by its exact build-generated hash; arbitrary inline code remains blocked. A built wheel includes UI assets and policy. Docker packaging, independent finish review and public 0.2.0 publication are being completed.

Public 0.1.1 was anonymously pulled and passed a paired ARM64 Docker roundtrip. Its release includes the physical Spark and publication verification receipts. This iteration changes the UI and packaging; hardware limits above remain.
