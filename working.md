# Popcorn SR — iteration 1

## Objective
Ship a usable standalone Docker manager and paired worker, with a guided web interface, single-host mode, configurable external scratch storage, optional native Windows RTX/DLSS adapters, and a public repository with clean main history.

## Acceptance
- Authenticated one-use pairing, durable queue, worker leases, cancel/retry, streaming transfers.
- Original library read-only; independently validated output, collision-safe publishing.
- CPU encode and conventional enhancement tested on actual media end to end.
- NVIDIA codecs and optional AI engines enabled by runtime smoke checks only.
- NAS, worker, single-host and NVIDIA Docker examples with ARM64/AMD64 builds.
- Browser desktop/mobile flows and error states verified.
- CI tests, Docker smoke, public commits on main as thekozugroup@gmail.com.

## Evidence and limits
Implementation in progress. This Mac has Docker and FFmpeg, but no NVIDIA GPU. Physical Spark, Optane mount behavior and RTX 5080 AI quality/speed remain device acceptance gates.

## Research
- DGX Spark has 1 NVENC / 1 NVDEC; ARM64 compatibility must be checked per SDK/runtime.
- fast-rtxvsr is MIT wrapper code with separately licensed NVIDIA runtimes; Windows requirements.
- Merserk Visual Enhancer is Windows/D3D12, source-available proprietary; reference and separately installed CLI only.
- Ordinary host USB-C ports do not provide a standard host-to-host network. Use Ethernet or an OS-supported bridge adapter.
