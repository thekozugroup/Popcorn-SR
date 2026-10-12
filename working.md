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
Version 0.1.0 software implementation is complete. Public repository: https://github.com/thekozugroup/Popcorn-SR. All development commits use main and thekozugroup@gmail.com, with no AI co-author tags.

Verified on 2026-10-12:
- Eight media/API tests: real encode/upload/download, checksums, source changes, lease exclusivity, cancel/retry, revoked workers, incompatible codecs, traversal, HDR and 16-bit SDR rejection, subtitle/attachment/chapter preservation, scratch identity changes, preview-to-full guards.
- Two Chromium workflows: actual five-second preview and full six-second video on a CPU worker, retained device/output/settings, authenticated download, login errors, pairing and keyboard navigation. Axe reported zero violations and no horizontal overflow in tested 390/768/1440 light/dark library/processing views.
- Linux ARM64 paired Docker containers: generated source → download → 2× resize/noise reduction → upload → validated output. Original checksum unchanged, audio preserved, scratch job files removed. Receipt and UI captures are under gitignored `evidence/`.
- NVIDIA codecs are absent on this CPU host, as expected; capability discovery genuinely encoded with CPU H.264/HEVC/AV1 instead of inferring support from a codec list.
- Official RealESRGAN_x4plus checkpoint SHA-256 verified; adapted RRDB architecture loaded it strictly and ran small tiled inference on CPU. This establishes model/network compatibility, not GPU video execution.
- NGC PyTorch 26.09-py3 registry manifest includes Linux AMD64 and ARM64. The larger optional AI image was not built or executed on a GPU here.
- Ruff, Tailwind build and npm high-severity dependency audit pass. GitHub verification includes Linux AMD64 Docker processing; the release workflow verifies its exact tagged commit before publishing both architectures.
- The independent Impeccable review scored preview-first setup, direct full-video continuation and queue action hierarchy resolved. Its named roles were unavailable, so fresh general agents used the shipped role instructions. Design context reported legacy PRODUCT.md headings; the established brief is preserved rather than migrated as a side effect.

This Mac has no NVIDIA GPU. Physical DGX Spark and RTX 5080 encode/inference, representative library quality, long jobs, HDR preservation, external-drive hot-unplug and real network throughput remain device acceptance gates. Native Linux DLSS rendering is not implemented; an experimental external engine contract is supplied. Transfers restart from the beginning after interruption.

## Next device acceptance
1. Inventory Spark/desktop architecture, drivers, Docker GPU access, external drive mount and free space.
2. Run actual NVENC and optional Real-ESRGAN/VFX engine checks; benchmark short representative SDR clips and compare temporal quality.
3. Test Unraid delivery, Optane scratch writes, cancellation, network interruption and mount/service dependencies before a whole-library run.

## Research
- DGX Spark has 1 NVENC / 1 NVDEC; ARM64 compatibility must be checked per SDK/runtime.
- fast-rtxvsr is MIT wrapper code with separately licensed NVIDIA runtimes; Windows requirements.
- Merserk Visual Enhancer is Windows/D3D12, source-available proprietary; reference and separately installed CLI only.
- Ordinary host USB-C ports do not provide a standard host-to-host network. Use Ethernet or an OS-supported bridge adapter.
