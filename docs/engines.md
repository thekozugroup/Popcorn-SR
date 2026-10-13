# Enhancement engines

An engine is advertised only after the worker encodes a small clip, runs the actual enhancement, checks dimensions/duration, and decodes the result. Installation or a GPU name alone never marks an engine ready.

## Conventional resizing

FFmpeg Lanczos scaling is available without AI. Optional `hqdn3d`, `bwdif`, `unsharp` and `minterpolate` filters perform noise reduction, deinterlacing, sharpening and 60 fps interpolation. These are conventional filters, not RTX Video or DLSS. Encoding uses the requested CPU or NVIDIA codec; a GPU failure stops the job rather than silently falling back.

## Real-ESRGAN on Linux

The integrated adapter uses the official RealESRGAN_x4plus model, checksum verification, `torch.load(weights_only=True)`, 192-pixel tiles with padding, CUDA inference and explicit system-FFmpeg NVENC encoding. PyAV decodes and sends timestamped raw frames through a NUT memory pipe, so its ARM64 wheel does not need NVIDIA encoder support. The pipe retains variable frame timestamps and processes one frame at a time. It writes no PNG frame sequence. Audio/subtitles/attachments are remuxed from the original afterward.

Install a compatible NVIDIA CUDA PyTorch runtime, `av`, `numpy` and Popcorn SR into the same environment. Set `POPCORN_ESRGAN_MODEL` to the checkpoint on the scratch drive. The optional `Dockerfile.ai` installs locked PyTorch 2.13.0 CUDA 13.0 wheels, PyAV 17.0.0 and NumPy 2.3.3 on Python 3.12. A verified ARM64 development package passed actual Unraid → Spark → Unraid AI previews in H.264, H.265 and AV1, plus full H.264 continuation. Audio/subtitle bytes, attachments, chapter timing, checksums and originals were preserved; test resources were removed. A fresh local image build also passed, without GPU execution on the Mac. These are short generated SDR checks; representative quality, long jobs, external-drive behavior and deferred RTX 5080 testing remain open. [Package provenance](../working.md).

This is image restoration applied frame by frame. It can create flicker or invented fine detail. Preview first. 2×/3× sizes resize the model's 4× result to the requested size. Different models, HDR, temporal restoration and face-specific models are outside this release.

## RTX Video through NVIDIA VFX

On Linux x86, install NVIDIA's `nvidia-vfx` wheel and compatible CUDA PyTorch/AV separately. Set `POPCORN_NVIDIA_VFX=1`. The built-in `popcorn_sr.nvidia_vsr` adapter calls the public `VideoSuperRes` API; source audio/subtitles are restored by Popcorn SR. No NVIDIA model/runtime is embedded in the default image. Follow NVIDIA's [VFX requirements](https://docs.nvidia.com/maxine/vfx/latest/LinuxVFXSDK/GetStartedonLinux.html) and the wheel's terms.

Public wheel inventory checked on 2026-10-12: NVIDIA VFX 0.2.0.0 provides Linux x86_64 and Windows AMD64/ARM64 wheels, but no Linux ARM64 wheel. Consequently this route is not promised on Linux DGX Spark. A separately compiled/vendor-supported ARM64 backend could use the external command contract below.

You can set `POPCORN_AI_PYTHON` to the interpreter containing the engine dependencies, but Popcorn SR must also be installed in that interpreter.

## DLSS 4 / 4.5 Super Resolution and DLSS 5

NVIDIA's [DLSS SDK](https://github.com/NVIDIA/DLSS) has Linux x86_64 and aarch64 libraries for Super Resolution, Ray Reconstruction and Frame Generation; the current [DLSS driver guide](https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/gaming.html) documents native Linux library loading. This is useful SDK plumbing, not a ready-to-run file upscaler. Video needs a renderer, temporal inputs/optical flow, timing and media integration.

The user's reference [Visual Enhancer](https://github.com/Merserk/dlss5-visual-enhancer) demonstrates adapting those features to video on Windows. It uses Direct3D 12 and separately licensed engine/runtime binaries. [Linux research bridges](https://github.com/ccoredesenvolvimento/dlss5-linux-bridge) demonstrate game/Proton neural rendering; they do not establish a turnkey headless ARM64 video backend.

**Popcorn SR 0.2.0 ships an experimental external adapter contract, not a native Linux DLSS renderer.** Set `POPCORN_DLSS_COMMAND` or `POPCORN_DLSS5_COMMAND` only when you have a working standalone video executable on that worker. A driver update does not create one. Custom adapters may use a native Linux SDK implementation or a separately provisioned compatibility environment; their dependencies and performance are the operator's responsibility.

DLSS Super Resolution supports source-size DLAA, 2× Performance, and 3× Ultra Performance in the included Windows adapter. DLSS 5 neural rendering keeps source dimensions and may modify appearance, lighting and detail. Select it consciously; it is not interchangeable with faithful restoration.

Development `main` now includes an independent experimental native CUDA DLSS SDR video bridge. It requires operator-provisioned NVIDIA SDK/runtime files; they are not bundled. It exposes verified DLAA/Quality/Balanced/Performance/Ultra Performance modes, preset hints and motion-estimation quality. The source manager gates advanced settings and preserves older recipes. See [native setup and limitations](../native/README.md). This development backend is not present in the published 0.2.0 image. Five-stage parity remains unfinished.

Development `main` also includes an independent native Vulkan DLSSG video backend. Physical Spark and dedicated ARM64 Docker tests passed H.264/H.265/AV1 output, native multi-frame generation and variable-rate timing. Worker/UI controls provide target rates from 23.976 to 480, Auto/Native/Cascade modes and motion quality. The rebuilt worker returned paired previews in all three codecs and a full-video continuation with original audio and intact sources. Native SR/DLAA → lossless FFV1 → DLSSG → selected export codec also passed actual Unraid → Spark → Unraid previews and full continuation with retained audio/subtitle packet bytes, attachments and chapter timing. Read-only SDK/driver mounts and conservative low-space refusal passed physical acceptance. Only combinations that pass real startup renders are offered; representative quality, long jobs and production deployment lifecycle remain pending. It needs separately provisioned NVIDIA components and is not in the published 0.2.0 image. [Build, package evidence and remaining limits](../native/README.md).

## External command contract

The worker operator, not a web request, configures a JSON array of arguments. It is executed directly, without a shell. Placeholder values are fixed by the validated job. Use `POPCORN_VSR_COMMAND`, `POPCORN_DLSS_COMMAND` or `POPCORN_DLSS5_COMMAND` for your separately installed engine:

```json
["/opt/my-video-engine", "--input", "{input}", "--output", "{output}", "--width", "{width}", "--height", "{height}", "--codec", "{codec}"]
```

This is a contract example, not an installed executable. Placeholders: `input`, `output`, `width`, `height`, `scale`, `codec`, `quality`. Produce one decodable video at the exact output path with exit code 0. Output codec must match `h264`, `hevc` or `av1`; output size and duration must match. DLSS 5 must keep source size. Audio/subtitles from the external exporter are discarded in favor of the source streams. Worker subprocesses receive scratch-based temporary/cache paths. Configure proprietary application caches separately if their own settings ignore those environment variables.

Every custom command is a trusted operator-controlled program. Do not accept command templates from untrusted sources. Support means the configured program passed a small real clip; representative library quality, all codecs, large resolutions and long-run behavior still require device tests.

## Secondary Windows adapters

For a future Windows deployment, install the engine yourself and set `POPCORN_FAST_RTXVSR` to its CLI or `POPCORN_VISUAL_ENHANCER` to `VE_CLI.exe`. Install FFmpeg and Popcorn SR with Python 3.12+. Do not redistribute Visual Enhancer inside Popcorn SR: its current license is source-available proprietary. [fast-rtxvsr](https://github.com/glarsson/fast-rtxvsr) is an MIT wrapper with separately licensed NVIDIA dependencies. The Linux path is the development priority; these adapters have not been tested on a Windows GPU in this iteration.

## Required feature parity

All five NVIDIA video stages, including RTX Video HDR and DLSS frame generation, are active completion requirements. Current experimental contracts do not fulfill them. See [the feature matrix and evidence gates](nvidia-parity.md).
