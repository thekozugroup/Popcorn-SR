# NVIDIA enhancement completion requirements

Popcorn SR's completion goal includes all five primary NVIDIA video enhancements from [Visual Enhancer](https://github.com/Merserk/dlss5-visual-enhancer). This is an implementation and device-verification requirement. The published 0.2.0 preview does not meet it yet.

| Required stage | User controls to support | Current implementation gap |
|---|---|---|
| DLSS neural rendering | Style, intensity, passes, tone/structure, masks, temporal quality | No native Linux video renderer or verified compatible neural runtime |
| DLSS Super Resolution | DLAA, Quality, Balanced, Performance, Ultra Performance; preset and temporal quality | Native CUDA SDR video backend and controls on development main; packaged paired delivery and representative quality remain unverified |
| RTX Video Super Resolution | Quality 1–4, scale or custom dimensions | Linux x86 VFX adapter; no verified Spark backend |
| RTX Video HDR | Contrast, saturation, middle gray, peak luminance, precision | SDR-to-HDR processing, 10-bit encoding and validation remain unfinished |
| DLSS frame generation | Target FPS, engine mode, optical-flow quality | Native DLSSG video processing and timing validation remain unfinished |

Stages must be independently selectable, with compatible combinations and ordering. A preview must exercise the same settings and backend as the full job. Each enabled stage must pass its own real processing check on the selected worker. Unsupported stages stay unavailable with an actionable reason; availability does not count as completion.

## Evidence required to close the goal

- Real SDK invocation and produced pixels for each NVIDIA stage. Conventional resize/interpolation/tone mapping cannot satisfy NVIDIA stage acceptance.
- Manager → worker → returned file tests for individual stages and supported combinations. Preserve the source checksum, audio, subtitles, attachments, chapters and timing.
- HDR results must contain actual 10-bit HDR pixels, correct color signaling and suitable metadata. A relabeled SDR stream fails acceptance.
- Generated frames must come from DLSSG, with the requested frame cadence and original duration. Reject a target at or below the incoming frame rate.
- Quality checks include moving detail, scene cuts, faces, text and light changes. A synthetic startup clip establishes execution, not representative library quality.
- Worker cancellation, restart, interrupted transfer, full/replaced scratch storage and clean shutdown must preserve originals and safely recover only owned temporary files.
- Linux NVIDIA workers must work both paired with a NAS and on the same host. The Unraid manager remains usable without a GPU. RTX 5080 device acceptance is deferred by the user; that does not waive implementation of any stage.

## Native Linux investigation

NVIDIA's [DLSS SDK](https://github.com/NVIDIA/DLSS/tree/374959484e79a640feaba44c93ac8cfb0a03f5b5/lib) contains Linux AMD64 and ARM64 libraries for Super Resolution, Ray Reconstruction and Frame Generation. The current inventory does not establish a native Linux neural-rendering runtime or complete RTX Video HDR backend.

On 2026-10-12, the physical DGX Spark initialized NGX through its ARM64 driver and successfully created a 128×96 → 256×192 DLSS Super Resolution feature using SDK 310.9.1. The CUDA capability query reported Super Resolution available, Video Super Resolution unavailable, and Frame Generation unsupported through that CUDA path. This does not rule out another supported API. A subsequent static-frame CUDA smoke check also passed DLSS evaluation and readback: all 196,608 output channel values were finite. Decoded-video integration and temporal image quality remain unverified.

The independently written [NGX diagnostic](../native/README.md) reports initialization and single-frame pixel verification separately from video readiness. Its test files, SDK copies and caches were created in RAM and removed. No SDK binary, proprietary reference implementation or extracted model weights are included in Popcorn SR's public source.

The subsequent independent native video bridge passed physical Spark processing of 48-frame, two-second generated SDR clips with H.264, HEVC and AV1 NVENC output. Each produced 384×256 from 192×128 input, with all frame timestamps matching exactly. A 38-frame variable-rate clip also retained exact timestamps. All 25 combinations of the five SR modes and Default/J/K/L/M preset hints passed three-frame SDK evaluation/readback checks; low/medium/high motion-estimation settings passed too. Native runtime shutdown/recreation was unstable, so each configuration uses a fresh subprocess. NVENC frame reordering is disabled in the timestamped AI pipe to avoid duplicated/shifted frame timestamps observed on this runtime. Test files, dependencies, SDK copies and caches were RAM-backed and removed; existing containers and images were preserved.

This establishes native SDR execution and timing on short synthetic clips. It does not establish representative library quality, faithful color reproduction, large-resolution/long-job behavior, the NGX Docker image on a physical GPU, or NAS → native SR worker → NAS delivery. These remain acceptance gates. No other NVIDIA stage is implied by Super Resolution passing.

Separately provisioned NVIDIA components retain their [own terms](https://github.com/NVIDIA/DLSS/blob/main/LICENSE.txt). A proprietary reference application is a behavioral reference, not permission to copy or redistribute its implementation. Architecture/runtime constraints remain open completion requirements.
