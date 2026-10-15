# Video restoration and Spark performance

Evaluation date: **15 October 2026**. These are bounded device experiments, not a new production engine release or a full-episode benchmark.

## What is slowing the installed worker

The DGX Spark can run GPU video processing. Its GB10 is exposed to the worker with compute, video and graphics access. The installed driver is 580.173.02; a separate native ARM64 PyTorch 2.13.0/CUDA 13.0 test executed BF16 CUDA operations on compute capability 12.1. Native DLSS and NVENC also executed successfully. No driver, clock or unrelated service settings were changed.

The current video DLSS adapter must estimate game-style motion vectors on the CPU. It decodes on the CPU, converts pictures, transfers each picture to the GPU and reads it back before encoding. It also initializes a new NGX session for each job. More memory does not remove those serial stages.

Fresh processes using the installed native image processed **48 generated pictures, 1920×1080 → 3840×2160**, with H.264 NVENC:

| CPU quota | Motion setting | CPU motion estimation | Synchronous GPU bridge | NGX initialization | Total | Pictures / total second |
|---|---|---:|---:|---:|---:|---:|
| 2 cores | High | 15.84 s | 3.17 s | 6.38 s | 27.19 s | 1.77 |
| 6 cores | High | 15.50 s | 3.02 s | 6.16 s | 26.44 s | 1.82 |
| 2 cores | Low | 0.88 s | 3.04 s | 6.25 s | 11.83 s | 4.06 |
| 6 cores | Low | 0.89 s | 3.08 s | 6.17 s | 11.69 s | 4.11 |

The bridge measurement includes conversion, validation, transfer, synchronous NGX execution and readback; it is **not** an isolated GPU-kernel measurement. Totals include startup, decoding and encoding, but exclude NAS transfer and manager validation. Generated pictures establish operation and stage costs, not film quality. These short cold runs cannot predict sustained library throughput.

Raising the CPU quota barely helped this test. The deployed limits remain **2 CPU cores and 12 GiB**. OpenCV motion estimation itself is bounded to two threads. On a 20-core host, a busy two-core worker can therefore look lightly loaded in a whole-machine CPU display. GPU temperature and an idle utilization snapshot do not establish whether a job is configured correctly.

There is also avoidable preview overhead: the worker currently transfers and verifies the **whole source file** before clipping a selected frame or short preview. Frame generation adds further timing checks and lossless intermediate videos. Neither extra CPU quota nor a faster upscaler alone removes these costs.

## ALF experiment

The existing authenticated library viewer supplied 17 consecutive requested frames from a 640×480, 29.97 fps ALF episode around 200 seconds. Requests were serial and read-only. The images were reconstructed into a lossless constant-rate sample on Spark. No NAS test file or queue entry was created. This checks a short real-content sample; it does not validate original episode audio, variable timing, scene changes or long-run memory use.

SeedVR2's 3B FP16 model produced **17 decoded pictures at 1440×1080**, retaining the sample's 29.97 fps and 0.567234-second picture duration. The isolated container took **122.14 seconds**, including process startup and model loading, or **0.139 output pictures/second**. Its own processing report was 112.08 seconds. This configuration is a restoration-quality candidate, not a speed improvement over the installed DLSS adapter.

The test used PyTorch SDPA, five-picture batches, one-picture overlap, 512-pixel tiled VAE decoding and a fixed seed. A live GPU-process query attributed about 10.4 GiB to the owned Python process. Whole-device sampling peaked at 96% utilization, 65.82 W and 70°C; those utilization/power readings also include any concurrent shared GPU work. The unrelated resident language model remained running.

For comparison, the same reconstructed ALF sample passed native DLSS to the same 1440×1080 dimensions: 8.83 seconds with high motion estimation and 7.37 seconds with low. NGX initialization alone accounted for 6.50 and 6.26 seconds respectively. These tiny cold samples are unsuitable for a full-episode time estimate.

## FlashVSR+ integration measurements

The pinned Turbo runtime executed on GB10 with its included **Triton block-sparse attention** operator. Its SDPA fallback refused this 1080p workload because the attention mask would exceed its allocation guard; no support is claimed for that fallback.

Upstream's streaming CLI moved the denoiser weights to CPU before each decoder segment. Keeping those weights on CUDA reduced the same 17-picture, 1536×1152 run from **119.56 to 32.38 seconds**. Every decoded RGB frame hash matched. An unmodified warm-cache control still took **119.28 seconds**, separating this improvement from compilation-cache effects. This is a 3.68× improvement over that specific upstream configuration, not over DLSS or a complete episode.

Popcorn's adapter pads rather than cropping the picture, streams bounded groups, preserves individual timestamps and declared SDR color, validates every decoded output picture, and exports separately through NVENC. The 17-picture ALF sample at **1440×1080** passed H.264 in **33.18 seconds**, H.265 in **32.61 seconds**, and AV1 in **34.27 seconds**. CUDA allocation peaked at 11,078,325,248 bytes. Each process loads the model and creates its own disposable compile cache; these are cold totals excluding NAS transfer and final manager validation.

A direct read-only episode extract, with 98 actual source pictures over approximately 3.24 seconds, passed AV1 at **768×576 in 32.18 seconds**. Its peak CUDA allocation was 5,777,611,776 bytes; both clock lookahead and the upstream input buffer peaked at **20 pictures**. The video adapter does not copy audio itself: the worker's preservation/remux stage must also pass installed acceptance before this becomes an advertised library workflow. A second 98-picture run at 1440×1080 passed H.265 in **91.96 seconds**, peaking at 11,545,746,432 CUDA bytes with the same 20-picture buffer. These short runs do not establish whole-episode stability or sustained throughput.

The existing Real-ESRGAN adapter also produced 17 ALF pictures at 1440×1080 in **24.75 seconds** using real CUDA and H.264 NVENC. Its per-frame approach is a separate baseline, with possible temporal flicker. All candidate timings include process startup; the FlashVSR upstream CLI measurements use 1536×1152, 13.8% more pixels than the 1440×1080 adapter tests.

## Engine candidates

| Candidate | Why consider it | Current boundary |
|---|---|---|
| [SeedVR2](https://github.com/ByteDance-Seed/SeedVR) | Video restoration designed for degraded footage; uses surrounding frames | Real ALF CUDA inference passed through the [standalone community CLI](https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler). Slow in the tested configuration. No production Popcorn adapter yet. |
| [FlashVSR+](https://github.com/OpenImagingLab/FlashVSR_Plus) | Newly released streaming video restoration with sparse attention | Real ARM64/GB10 Turbo Triton inference and the Popcorn adapter passed bounded ALF samples. Optional integration is under acceptance; whole-episode speed and quality remain unmeasured. |
| [ReCaVSR](https://github.com/kopperx/ReCaVSR) | Recent streaming restoration research | Authors report 21.2 fps at 1080p on an A100-80GB, not a Spark or RTX 5080. The released x86-64 environment and full-clip reader/writer still need ARM64 and long-video adaptation. [Paper](https://arxiv.org/abs/2609.37831). |
| [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) | Existing lightweight Popcorn AI adapter and useful baseline | Frame-by-frame restoration can flicker. It is not a temporal video model or RTX Video Super Resolution. |

FlashVSR+ code was released on 14 October following its [13 October paper](https://arxiv.org/abs/2610.17552). Its portable SDPA path failed the measured large-mask guard; the included Triton operator succeeded without an external CUDA extension. Its CLI requires dimensions divisible by 128 and can crop/resize; a production adapter must preserve the source aspect ratio and verify picture clocks, color, audio and subtitles. A CLI sample succeeding is insufficient to advertise full library support.

Generative restoration may invent detail or change faces, writing and textures. Review matched frames and motion before processing a library. Keep game-oriented DLSS experimental; use video-specific models for restoration work.

## RTX 5080 expectations

NVIDIA's [Windows VFX performance reference](https://docs.nvidia.com/maxine/vfx/latest/WindowsVFXSDK/PerformanceReference.html), updated 22 September 2026, measures 720p → 1440p VSR at 0.688 ms/2.01 ms for Medium/Ultra on RTX 4090, and 0.642 ms/1.67 ms on RTX 5090. These are effect latencies, **not file-processing rates**, and neither column measures RTX 5080. Its RTX Spark column is Windows ARM64 and is not evidence for this DGX Spark Linux installation.

With a compatible runtime and GPU-resident decoding, VSR and encoding, real-time or faster processing is plausible for the desktop. A measured 30/60/120 fps would process a 30 fps video in approximately its full/half/quarter running time, plus transfer and validation. Those are arithmetic examples, not promised RTX 5080 speeds; 4K output and quality mode need their own measurements.

Linux compatibility is a separate gate: the current [Linux VFX installation guide](https://docs.nvidia.com/maxine/vfx/latest/LinuxVFXSDK/InstalltheVFXSDK.html) distributes core/features through NGC and lists specific server GPU targets. Neither RTX 5080 nor GB10 appears in its supported installer target list. Do not infer a supported Linux VSR runtime from the GPU's DLSS capability. The desktop has not been accessed or benchmarked in this iteration.

The [RTX 5080](https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5080/) has 16 GB GDDR7 and 960 GB/s memory bandwidth. [DGX Spark](https://docs.nvidia.com/dgx/dgx-spark/hardware.html) provides much more capacity with 273 GB/s unified-memory bandwidth. Capacity helps a model fit; it does not guarantee faster inference. The bandwidth ratio is not an FPS multiplier.

## Reproducibility and release gate

Evaluated SeedVR2 CLI revision: `4490bd1f482e026674543386bb2a4d176da245b9`.
Model repository: `numz/SeedVR2_comfyUI`, revision `09ced71023636e9bc8cdf9cdecfb2625d1e691e8`.

| File | SHA-256 |
|---|---|
| `seedvr2_ema_3b_fp16.safetensors` | `2fd0e03a3dad24e07086750360727ca437de4ecd456f769856e960ae93e2b304` |
| `ema_vae_fp16.safetensors` | `20678548f420d98d26f11442d3528f8b8c94e57ee046ef93dbb7633da8612ca1` |

A replacement needs bounded streaming, cancellation, truthful progress, exact picture count/timing and color checks, original audio/subtitle preservation, startup capability tests and paired NAS acceptance. Keep installed capabilities unchanged until those gates pass. Test inputs, exported frames, raw logs, temporary dependencies and unused checkpoints must be removed after evaluation; never delete library originals or unrelated services/caches.

## Optional restoration worker (development)

This method is explicit; Auto keeps the existing enhancement priority. HDR input, ten-bit input and combining restoration with HDR/frame generation are rejected. A real startup render gates each of H.264, HEVC and AV1 separately. Output dimensions are padded internally and cropped back to the requested aspect-preserving size; model padding never crops the source. GPU memory exhaustion fails the job rather than switching to CPU. Successful small checks do not guarantee enough memory for 4K.

Build `Dockerfile.restoration` on a Linux ARM64/AMD64 Docker host. It includes the pinned public runtime, CUDA PyTorch and existing native-DLSS adapter; no model weights or NVIDIA SDK files are bundled. Install approximately 7.0 GB of pinned weights once in a deliberate persistent folder using:

```sh
python -B -m popcorn_sr.restoration_assets models /your/persistent/models/flashvsr
```

The optional `compose.restoration.yaml` overlays `compose.worker.yaml`, or the same-machine layout, and mounts `RESTORATION_MODELS_PATH` read-only. Add `compose.ngx.yaml` before the restoration overlay if retaining separately installed DLSS. The restoration worker allows six CPU cores and 32 GiB RAM because model loading/compilation needs more memory than the native-only worker. The CUDA allocator also has a dynamic ceiling capped at 20 GiB. Keep sufficient headroom for other services; Spark's 128 GB is shared CPU/GPU memory.

Pair normally, wait for genuine checks, choose **FlashVSR+ video restoration**, then test a short motion sample. Model weights and the installed runtime are final application assets; downloads, generated videos, compiler caches and diagnostic logs are disposable. Each restoration job puts its compiler/model caches in its owned work folder and removes them when the job ends. The host updater supports the separate `restoration-stable` image channel and refuses updates that lose verified engines or codecs. No Docker socket is given to the worker.
