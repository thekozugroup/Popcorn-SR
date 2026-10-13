# Native NVIDIA diagnostics

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

The actual Spark test passed initialization, feature creation, evaluation, synchronization and readback; all 196,608 output channel values were finite. Temporal motion estimation, scene-cut resets, decoded-video timing, representative quality and manager integration remain unfinished. This check does not enable DLSS in the production UI.
