# One-container Spark worker

The Spark runs one Popcorn worker. FlashVSR+, PyTorch/CUDA, FFmpeg, NVENC adapters and the pinned model installer are in the published restoration image. There is no model server, inference sidecar, queue service or host Python environment to install. The NAS keeps its separate lightweight manager.

Model weights are persistent application data, not another container. Keeping the 7.0 GB download outside image layers means replacing the worker does not download it again. Inference checks the pinned hashes and never changes or downloads weights. The dedicated model mount is writable so the same container can install missing weights explicitly. Container root and licensed native runtimes stay read-only.

The existing Spark installation already uses one resolved Compose file and retains its native DLSS mounts and host updater. Do not replace an existing installation's state, scratch identity or native configuration with the fresh-install example below.

SeedVR2 was evaluated as a temporary experiment and is not installed. Adding it later requires a packaged worker adapter and built-in model installation, not a separate ComfyUI or inference server.

## Fresh installation

Install Docker, NVIDIA's driver and Container Toolkit first. Use `compose.spark.yaml` by itself with the published image; no source build or Compose overlays are needed for FlashVSR+. Create three private host folders owned by your chosen numeric worker UID/GID: state, scratch and models. Mount the intended scratch drive before creating its folder. Missing folders are never created by Compose.

Set a private `.env` beside that file:

```dotenv
POPCORN_MANAGER=http://NAS-IP:8787
POPCORN_WORKER_NAME=DGX Spark
PUID=1000
PGID=1000
WORKER_STATE_PATH=/home/your-user/popcorn-sr/state
SCRATCH_PATH=/your-mounted-drive/popcorn-sr/scratch
RESTORATION_MODELS_PATH=/home/your-user/popcorn-sr/models/flashvsr
```

Use the actual paths and numeric IDs. Run setup once through the worker image:

```sh
docker compose -f compose.spark.yaml run --rm --no-deps --entrypoint /bin/sh worker -ec \
  'popcorn-sr init-scratch /scratch && python -B -m popcorn_sr.restoration_assets models /models/flashvsr'
```

This temporary setup invocation exits and is removed; it is not an additional running service. Downloads are verified and atomically installed. Repeating the installer verifies existing files without downloading them. Corrupt or different existing files are preserved and reported rather than overwritten. Download fragments are removed on normal completion or failure. No host Python or Hugging Face cache is used.

After the download, obtain a fresh pairing code in the NAS Web UI and add `POPCORN_PAIR_CODE=your-code` to `.env`. Start the one worker:

```sh
docker compose -f compose.spark.yaml up -d --no-build
```

Pairing appears before processing checks finish. Complete startup checks took about ten minutes on the installed Spark. Wait for verified methods, then choose **FlashVSR+ video restoration** and preview a frame and motion sample. Remove the consumed one-use code from `.env` after pairing; saved pairing survives normal replacements. No inbound Spark port or NAS library share is needed.

## Model installation in the running worker

On an idle worker deployed with the writable model mount:

```sh
docker compose -f compose.spark.yaml exec worker \
  python -B -m popcorn_sr.restoration_assets models /models/flashvsr
```

Restart only if this installed models that were missing during the worker's startup checks. Never run a second worker against the same state folder. Existing advanced layouts may intentionally mount models read-only; enable writes only for the dedicated model mount before using the installer. Scratch files and compiler caches remain disposable and are cleaned after jobs; model weights persist across image updates.

Native DLSS retains separately authorized SDK/driver mounts. The host NVIDIA driver is still required. The optional [update controller](updates.md) is a small host service that replaces this one worker after its current job; it is not an inference sidecar. Update requests originate inside the container, which receives no Docker socket. Atlas continues using its native Unraid updater.

## Measured memory

Observed on the installed 0.5.0 Spark worker on 15 October 2026:

| Measurement | Observed amount | Meaning |
|---|---:|---|
| Container lifetime `memory.peak` | 15.49 GiB | Cgroup-reported system-memory peak across startup and the preceding ALF tests, including charged cache |
| ALF render peak CUDA allocation | 10.75 GiB | PyTorch allocation high-water mark for 149 pictures, 640×480 → 1440×1080 |
| Latest restart-check peak | 14.84 GiB | Fresh complete startup checks after the model-mount change |
| Idle Docker display | About 0.3–0.5 GiB | Excludes inactive file cache; latest snapshot was 514 MiB |
| Idle cgroup including cache | 7.53 GiB | Immediately after verification; about 7.01 GiB was inactive file cache and can be reclaimed |
| Container memory ceiling | 32 GiB | Limit, not a reservation or measured requirement |
| CUDA allocator ceiling | At most 20 GiB | Additional dynamic per-process safeguard, not preallocated memory |
| Swap / OOM events | 0 / 0 | No swap use or memory-limit kills observed |
| Persistent model files | 7.02 GB / 6.53 GiB on disk | Three pinned files; this is storage, not an extra RAM reservation |

Spark's CPU and GPU share physical memory ([NVIDIA architecture](https://docs.nvidia.com/dgx/dgx-spark-porting-guide/overview.html)). Cgroup and CUDA statistics have different accounting scopes: do not add these peaks or interpret either as a complete driver-inclusive physical-memory measurement. The CUDA counter excludes some runtime/driver overhead. Keep the 32 GiB ceiling for loading/compilation headroom; a lower safe limit was not established. Full episodes and 4K restoration remain unmeasured.
