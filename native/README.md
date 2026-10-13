# Native NVIDIA video adapters and diagnostics

`ngx_probe.cpp` independently checks NGX driver initialization, capability queries and creation of a small DLSS Super Resolution feature. An optional single-frame pixel smoke check is available. It always reports `video_render_verified: false`: initialization alone must never enable a video engine. It is separate from the production worker and licensed under [MIT](LICENSE).

Obtain NVIDIA's DLSS SDK separately and review its terms. The probe needs `include/nvsdk_ngx_defs.h` and `include/nvsdk_ngx_params.h`, the matching Linux runtime libraries, an NVIDIA driver, and a C++17 compiler. No NVIDIA source or binary is supplied here.

Example on a Linux NVIDIA worker, with the SDK already present:

```sh
# Keep the binary, driver data and caches on the chosen scratch drive.
export SDK_ROOT=/path/to/operator-installed-DLSS-SDK
export PROBE_SCRATCH=/path/to/mounted-scratch/ngx-check
mkdir -p "$PROBE_SCRATCH"
chmod 700 "$PROBE_SCRATCH"
g++ -std=c++17 -O2 -I "$SDK_ROOT/include" native/ngx_probe.cpp \
  -ldl -o "$PROBE_SCRATCH/ngx-probe"
# Use Linux_aarch64 on Spark; Linux_x86_64 on an x86 desktop.
export NGX_RUNTIME_PATH="$SDK_ROOT/lib/Linux_aarch64/rel"
HOME="$PROBE_SCRATCH" TMPDIR="$PROBE_SCRATCH" \
  XDG_CACHE_HOME="$PROBE_SCRATCH" CUDA_CACHE_PATH="$PROBE_SCRATCH/cuda" \
  LD_LIBRARY_PATH="$NGX_RUNTIME_PATH${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$PROBE_SCRATCH/ngx-probe" "$NGX_RUNTIME_PATH" "$PROBE_SCRATCH"
```

Inspect each result field. `0x00000001` means that particular SDK operation succeeded. The process exit code describes initialization only; it does not imply that all queried features or SR creation succeeded. A capability failure on CUDA does not establish that a Vulkan or Direct3D backend cannot work.

Remove the owned probe folder after checking it; do not clear shared GPU caches, images or application data. Actual video integration must validate pixel output, temporal inputs, media timing and encoding separately. See the [five-stage completion requirements](../docs/nvidia-parity.md).

## Single-frame render proof

When CUDA Toolkit headers are installed, compile with `-DPOPCORN_CUDA_SMOKE -I /usr/local/cuda/include` added to the command above. Add `--render` after the two probe arguments. The optional check allocates input color, depth and zero motion for a static synthetic frame, writes DLSS output to a writable CUDA surface, and reads back all 256×192 RGBA float pixels. Output starts as NaN; finite readback confirms that the SDK wrote pixels. `pixel_render_verified: true` describes this one frame only.

The actual Spark test passed initialization, feature creation, evaluation, synchronization and readback; all 196,608 output channel values were finite. This diagnostic does not enable DLSS in the production UI. The subsequent video adapter and its separate acceptance boundary are described below.

## Experimental SDR video bridge (development main)

`dlss_sr.cpp` is an independently written MIT bridge with a small C ABI. It uploads float RGBA and estimated current-to-previous motion, invokes NVIDIA's actual CUDA Super Resolution feature, and reads back a writable CUDA output surface. `popcorn_sr.dlss_sr` decodes 8-bit SDR video, estimates dense motion, resets on cuts/time gaps, checks every output channel for finite pixels and streams timestamped frames into system FFmpeg NVENC. It never falls back to another renderer. Captured video supplies no original game-engine depth or jitter: flat depth and zero jitter make this an experimental adaptation, not a promise of faithful restoration.

The bridge permits one NGX session per process lifetime. The tested runtime could not safely recreate a feature after shutdown; settings checks therefore use fresh subprocesses. A worker job already uses an isolated adapter process. This boundary also releases native GPU resources at process exit.

Build on the intended worker architecture, using separately obtained NVIDIA SDK and CUDA headers:

```sh
# SDK_ROOT points to the operator-installed SDK; NGX_BUNDLE is a chosen persistent
# installation folder, separate from disposable job folders. No SDK is vendored.
mkdir -p "$NGX_BUNDLE"
g++ -std=c++17 -O2 -Wall -Wextra -Werror -fPIC -shared \
  -I "$SDK_ROOT/include" -I /usr/local/cuda/include native/dlss_sr.cpp \
  -ldl -o "$NGX_BUNDLE/libpopcorn-dlss.so"
# Provision the matching libnvidia-ngx-dlss.so runtime in NGX_BUNDLE separately,
# under its NVIDIA terms. Keep its versioned filename and .so symlink intact.
```

The current test SDK is pinned to [3749594](https://github.com/NVIDIA/DLSS/tree/374959484e79a640feaba44c93ac8cfb0a03f5b5), runtime 310.9.1. Use `lib/Linux_aarch64/rel` on Spark, `lib/Linux_x86_64/rel` on an x86 desktop. The native bridge needs only the driver APIs; it does not require PyTorch.

For a native worker, install `uv sync --extra ngx`, set `POPCORN_NGX_LIBRARY` to the built bridge and `POPCORN_NGX_RUNTIME` to the runtime folder. Put the SDK and host-driver NGX libraries on the process's library search path **before starting Python**. `POPCORN_NGX_PYTHON` optionally selects the interpreter containing Popcorn SR and its pinned NGX dependencies.

For Docker, build `Dockerfile.ngx` and layer `compose.ngx.yaml` over the paired or single-host worker configuration. Set `POPCORN_NGX_BUNDLE` and `POPCORN_NGX_DRIVER` (the host's `libnvidia-ngx.so.1` path). Both are read-only mounts; NVIDIA Container Toolkit provides the GPU/encoding driver. This image is a local development build, not the published 0.2.0 image. Its physical acceptance is tracked in `working.md`.

The worker tests a real video before advertising DLSS. It then checks all 25 mode/preset pairs and all three motion-estimation qualities using decoded frames and real SDK evaluation/readback. Initialization can take several minutes. Controls only expose the combinations that passed, and jobs cannot be claimed by a worker that has not verified their settings. Presets are SDK hints; NVIDIA may select a compatible model. Existing 1×/2×/3× recipes retain their DLAA/Performance/Ultra Performance behavior. Explicit Quality and Balanced modes use about 1.5× and 1.72× sizing, rounded to even encoder dimensions.

Representative image quality, color accuracy, long jobs and failure behavior require further device acceptance. The other four NVIDIA stages remain separate completion requirements.

Physical Spark video evidence: 48-frame, two-second 192×128 clips produced 384×256 H.264/HEVC/AV1, each with exact source frame timestamps. A 38-frame variable-rate clip retained exact timing too. All 25 mode/preset hint pairs and three motion-estimation qualities passed actual three-frame SDK checks. Pixel buffers are checked for finite values before encoding. These tests used an existing CUDA container with RAM-backed pinned dependencies and SDK files, not the new NGX Docker image. All owned test resources were removed, and the existing service/image inventories were preserved.

Subsequent dedicated-package acceptance passed on Spark using the ARM64 NGX image built from `3be022b7620c2c6fccbb88cb42768e93f82c94dd`. Its imported filesystem layers, environment and architecture matched the local image. Startup verified all 25 mode/preset pairs in about 289 seconds. A paired Mac manager received five-second generated previews with audio: H.264/Performance/Default/high motion at 320×192, HEVC/Quality/K/medium at 240×144, and AV1/DLAA/J/low at 160×96. Download hashes matched, the original checksum was unchanged and no job folders remained. The temporary image/container and all owned RAM files were removed; existing service/image inventories matched. This used an SSH reverse tunnel, not a NAS/LAN benchmark. The published 0.2.0 image remains unchanged.

## Headless Vulkan frame-generation diagnostic

`ngx_vulkan_probe.cpp` checks extension discovery, the selected NVIDIA physical device, feature requirements, NGX initialization and capability parameters. With `fg --create`, it creates a small 256×192 RGBA8 Frame Generation feature and submits its initialization command buffer. The optional `--render` check evaluates synthetic pixels; the diagnostic always reports `video_render_verified: false`. This is separate from the video adapter below and does not enable a worker engine.

Build against separately provisioned NVIDIA SDK headers/static wrapper and Vulkan headers on the intended architecture:

```sh
# Use Linux_x86_64 on an x86 worker. The SDK wrapper supplies the typed public API;
# direct driver exports can have different signatures and must not be substituted.
g++ -std=c++17 -O2 -Wall -Wextra -Werror -I "$SDK_ROOT/include" \
  native/ngx_vulkan_probe.cpp "$SDK_ROOT/lib/Linux_aarch64/libnvsdk_ngx.a" \
  -Wl,-l:libvulkan.so.1 -ldl -pthread -o "$PROBE_SCRATCH/ngx-vulkan-probe"
HOME="$PROBE_SCRATCH" TMPDIR="$PROBE_SCRATCH" \
  XDG_CACHE_HOME="$PROBE_SCRATCH" CUDA_CACHE_PATH="$PROBE_SCRATCH/cuda" \
  __GL_SHADER_DISK_CACHE_PATH="$PROBE_SCRATCH/shaders" \
  LD_LIBRARY_PATH="$NGX_RUNTIME_PATH${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$PROBE_SCRATCH/ngx-vulkan-probe" "$NGX_RUNTIME_PATH" "$PROBE_SCRATCH" fg --create
```

The probe requires Vulkan 1.3. Inspect every operation result; exit zero means the requested diagnostic operations completed, not that video output exists. Failed feature-requirement queries report null support flags, so untouched zero-valued output cannot be mistaken for support. Without `--create`, successful capability discovery can still report an unavailable feature. Remove only the owned scratch folder afterward.

Physical Spark evidence on driver 580.173.02 and SDK 310.9.1: Vulkan found GB10, all required extensions were present, Frame Generation requirements reported supported, its availability and initialization values were successful, and actual feature creation plus command submission/wait passed. CUDA's earlier unsupported result did not apply to this Vulkan path. The SDK/library copies, executable and driver caches were temporary RAM files; the owned container was removed and existing service/image inventories matched. No new Docker image or NAS resource was created. The test used the host's matched Vulkan loader/driver libraries inside an existing image; it does not validate future production Vulkan packaging. Subsequent pixel and video checks are described below.

For a generated-frame pixel check, add `-DPOPCORN_VULKAN_SMOKE` when compiling and use `fg --render`. The separately provisioned SDK must also supply its DLSSG helper/parameter headers. The independent [Vulkan resources](vulkan_frames.hpp) upload RGBA8 color, flat float depth and backward pixel motion, synchronize with fences, and copy the output back. The output image is seeded on the GPU before each evaluation, and a separate GPU buffer reports whether NVIDIA disabled interpolation. Captured video supplies no original game-engine geometry; this remains an experimental adaptation.

This three-frame check passed on the physical Spark. The reset frame copied the input and disabled interpolation, as expected. Both subsequent moving frames reported interpolation enabled, replaced all 49,152 seeded output pixels and differed from both adjacent inputs. SDK evaluation, synchronization and readback all succeeded. `pixel_render_verified: true` proves these synthetic generated frames; the diagnostic's `video_render_verified` remains false. The owned RAM SDK/resources/caches and container were removed, with existing service/image inventories preserved. The separate video adapter below has its own evidence; long jobs, representative quality and worker delivery remain acceptance gates.

## Experimental Vulkan DLSSG video bridge (development main)

`dlssg.cpp` independently implements an MIT C ABI over NVIDIA's typed Vulkan SDK wrapper. `popcorn_sr.dlssg` decodes 8-bit SDR video, estimates backward pixel motion and supplies flat depth with an orthographic camera. Each intermediate frame comes from a real DLSSG evaluation. The adapter checks NVIDIA's disable-interpolation decision, resets history at cuts/time gaps and encodes through system FFmpeg NVENC. A disabled pair can contain repeated source pixels: this is the SDK's decision, not a substitute interpolation filter. Captured video lacks original game geometry, so this remains experimental.

Build on the intended Linux worker using separately provisioned SDK headers, the architecture-matched static wrapper, Vulkan headers and loader:

```sh
# SDK_ROOT/include holds the NVIDIA headers. Use Linux_x86_64 on x86 workers.
# VULKAN_INCLUDE points to the directory containing vulkan/vulkan.h.
g++ -std=c++17 -O2 -Wall -Wextra -Werror -fPIC -shared \
  -fvisibility=hidden -Wl,--exclude-libs,ALL -static-libstdc++ -static-libgcc \
  -I "$SDK_ROOT/include" -I "$VULKAN_INCLUDE" native/dlssg.cpp \
  "$SDK_ROOT/lib/Linux_aarch64/libnvsdk_ngx.a" \
  -Wl,-l:libvulkan.so.1 -ldl -pthread -o "$NGX_BUNDLE/libpopcorn-dlssg.so"
# Provision libnvidia-ngx-dlssg.so and the host NGX driver separately.
LD_LIBRARY_PATH="$NGX_BUNDLE${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  uv run --extra ngx python -m popcorn_sr.dlssg \
  --input /path/to/source.mkv --output /mounted-scratch/generated-video.mkv \
  --library "$NGX_BUNDLE/libpopcorn-dlssg.so" --runtime "$NGX_BUNDLE" \
  --factor 2 --temporal-quality high --codec hevc --quality 20
```

The current NVIDIA SDK/runtime pins match SR above. Compile-only CI obtains those pinned headers and Khronos Vulkan headers temporarily; it never downloads a proprietary runtime or claims GPU execution from compilation. `scripts/check-native-source.py --download-headers` checks both Vulkan sources and removes its temporary files.

`--factor` accepts integer multipliers 2–8, subject to the runtime's actual maximum. The Spark runtime reported five generated frames per source pair, permitting 2×–6×. All intermediate indices are evaluated in order, and later indices retain NVIDIA's per-pair disable decision. Output preserves each source-frame timestamp and spaces generated frames rationally within its interval. The final interval holds the last image through another SDK evaluation. The output clock includes both source container ticks and the frame-rate denominator; NVENC frame reordering stays disabled.

Physical Spark checks passed a 48-frame, two-second 192×128 clip in H.264/high motion, HEVC/medium and AV1/low, each producing 96 decoded frames. Native 3×, 4×, 5× and 6× produced 144, 192, 240 and 288 frames. A 38-frame variable-rate clip produced 76 frames. Decoded timestamps differed from their exact rational positions by at most 0.5 ms, within Matroska's millisecond precision; reported durations differed by at most 1 ms. Every output fully decoded. These tiny generated clips establish execution and cadence, not HD throughput or representative quality.

These tests used an existing container and matched host Vulkan loader/graphics libraries mounted read-only. SDK files, dependencies, compilation, videos and driver caches stayed in owned RAM storage. All test resources were removed, and existing service/image inventories matched. This does not verify the new NGX image's graphics-driver packaging. The NAS was untouched.

This CLI currently produces a **video-only intermediate**, with no worker/UI integration or audio/subtitle remux. It supports 8-bit SDR with square pixels and even dimensions; other inputs fail explicitly. Arbitrary target FPS, cascade modes, stage combinations, media preservation, paired delivery, long jobs and representative quality remain required work. The published 0.2.0 image does not contain this backend.
