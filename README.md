# Popcorn SR

**Keep your library on the NAS. Process videos on the computer with the power.**

Popcorn Super Resolution runs as a lightweight Docker manager plus a processing worker. Pair an Unraid NAS with a DGX Spark or NVIDIA Linux desktop, or run both services on one computer. Finished copies return to your chosen output folder. Originals remain untouched.

## Preview before a batch

The workspace puts input on the left, the output queue on the right and settings underneath. Select a video or batch, choose a video and time, then **Preview frame**. Compare large Original/Enhanced images or **Expand preview**, then choose **Run full video** or **Run full batch**. Changing the frame or processing settings requires a fresh comparison. Completed previews reopen from the queue.

Still comparisons process a video-only sample of up to five seconds, then display its first picture. Review the downloadable video sample for motion. Full runs restore the normal audio/subtitle/attachment/chapter checks and verify the saved source again.

## Install the 0.3.1 Docker preview

Download the kit matching each computer from [Releases](https://github.com/thekozugroup/Popcorn-SR/releases/tag/v0.3.1): **AMD64** for Unraid/x86 Linux, **ARM64** for DGX Spark. Each kit includes prebuilt manager/base-worker and native-worker images. No build on the NAS is required.

1. Verify the archive and load the selected image using [release-kit instructions](docs/releases.md).
2. Set your existing library, output and state folders, ownership IDs and private access key.
3. Start the manager, open its Web UI and choose **Devices & storage → Connect a worker**.
4. On the processing computer, configure and initialize its mounted scratch folder, then pair with the one-use code.
5. Preview one frame or a short sample before running a batch.

Use UID/GID **99/100** for ordinary Unraid share ownership. The loader only imports images; it does not change NAS templates, mount drives or start services. Use the kit's image selections and `--pull never`. The public registry supplies **0.3.1** as `ghcr.io/thekozugroup/popcorn-sr:0.3.1` and the native worker as `ghcr.io/thekozugroup/popcorn-sr:ngx-0.3.1`; both passed anonymous pulls. [Detailed deployment](docs/deployment.md) includes manual Unraid installation, paired and single-host layouts.

## Processing options

Choose **H.264**, **H.265 / HEVC** or **AV1** independently of the enhancement. Upscaling changes frames; encoding compresses those frames into the finished Matroska (`.mkv`) copy. H.264 offers broad player compatibility; check HEVC/AV1 support on your players. Available codecs and enhancement controls require real worker processing checks.

| Option | Current support | Additional installation |
|---|---|---|
| Conventional resizing, noise reduction, deinterlacing and sharpening | CPU or NVIDIA encoding | FFmpeg is included |
| Real-ESRGAN AI restoration | Optional CUDA worker, verified Spark execution | Larger AI image and official checksum-verified model |
| DLSS Super Resolution | Experimental native Linux CUDA adapter; Spark execution verified | Separately licensed NVIDIA runtime and native bridge |
| DLSS frame generation | Experimental native Linux Vulkan adapter; Spark execution verified | Separately licensed NVIDIA runtime and native bridge |
| RTX Video Super Resolution / HDR | Implemented adapters and controls; enabled only after genuine runtime checks | Compatible additional VFX runtime; current public Python wheels lack Linux ARM64 |
| DLSS neural rendering | Deferred | Authorized compatible beta SDK/runtime unavailable |

No proprietary NVIDIA runtime or AI model is bundled. Follow [native setup](native/README.md), [AI setup](docs/deployment.md#add-open-source-ai-on-spark-or-desktop), and [engine integration](docs/engines.md). Windows and physical RTX 5080 testing are deferred.

Video DLSS uses estimated motion, flat depth and zero jitter because films lack game-engine inputs. It can soften or alter detail; a successful processing check does not mean it improves every title. Short animation, effects and live-action trials provide bounded review evidence, not a library-wide quality guarantee. Version 0.3.1 preserves known BT.709/BT.601 SDR range and signaling through the tested paths. Unknown labels stay unknown; unsupported or conflicting profiles fail. Generated motion and appearance still need review. Review on the intended player before a library batch. HDR/high-bit-depth input safety gates remain; selecting a codec does not create HDR or enable an unavailable enhancement. [Roadmap and evidence](docs/nvidia-parity.md).

## Storage and connections

Scratch files and model/cache folders can live on a mounted external Optane drive. The worker retains the scratch filesystem identity and stops if it disappears or changes. Configure the host's mount dependencies too. Docker image layers use Docker's own data directory; move that storage separately if built-in drive endurance matters. Physical Optane acceptance remains pending.

Ethernet through a router/switch or reachable direct Ethernet works. 1 GbE is usable; 10 GbE shortens large transfers when both ends support it. Wi-Fi works, but connection loss can stop a job and require retry. Ordinary host USB-C ports do not establish a network through a plain cable. A USB-C enclosure can provide scratch storage. [Hardware and networking](docs/hardware.md).

## Verification and development

The 0.3.1 release kits are built locally from their recorded commit, checksum-verified, reloaded and exercised through paired CPU delivery on native ARM64 and emulated AMD64. Verification includes selected-frame/full continuation, copied audio, intact originals and concurrent 4K frames within a 512-MiB manager limit. All 127 Python tests, ten browser workflows, nine Compose configurations, native syntax, UI build and dependency audit pass. Genuine Spark acceptance covers 12 SR color/codec cases, four AI exports, fresh SR/FG startup checks, three paired SR+FG frame previews and full AV1 continuation. These generated trials establish processing, timing and color preservation, not film improvement. These are preview acceptance results, not unrestricted speed or whole-library benchmarks. [Current work and exact evidence](working.md).

```sh
uv run python scripts/verify-local.py
```

Install `uv`, Node.js, FFmpeg, a C++17 compiler and Docker. Linux may also need Chromium's system dependencies. The command checks source, UI/browser flows, images and real Docker processing/lifecycle behavior; it writes an ignored receipt and uses unique image tags. `--software-only` is partial verification; `--include-ai` also builds the larger CUDA image. Actual GPU acceptance needs a device. [Local packaging](docs/releases.md#local-packaging).

GitHub workflows are manual fallbacks; pushes, PRs and version tags do not launch them. Current releases use local builds and GitHub release files.

The UI uses official [Astryx](https://astryx.atmeta.com/) React components, zinc surfaces, blue-500 actions and system fonts. Vite builds static assets served by the Python manager, with no Node server or CDN at runtime. Rebuild with `npm run build` after UI changes. [Architecture](docs/architecture.md) · [Rust assessment](docs/rust-assessment.md).

## License and family

Popcorn SR is AGPL-3.0-or-later. NVIDIA SDKs and third-party engines retain their own terms. [Third-party notices](THIRD-PARTY-NOTICES.md) record BasicSR, Real-ESRGAN, Astryx and brand attribution. [fast-rtxvsr](https://github.com/glarsson/fast-rtxvsr) and [Visual Enhancer](https://github.com/Merserk/dlss5-visual-enhancer) informed the engine interface; their separately licensed runtimes are not redistributed. Design uses [Taste](https://tasteskill.dev) and [Impeccable](https://impeccable.style).

SR uses [Popcorn Batch's three-circle mark](https://github.com/thekozugroup/Popcorn-Batch/blob/54170f2684f734712b6159ccc7592f3237fa6b71/web/src/app/icon.svg), highlighting the lower-right circle in Tailwind teal-500. Action colors stay blue. Rust remains a candidate for measured worker/frame-handling improvements; no rewrite or unmeasured speedup is claimed.

Development main adds optional worker update requests and a host controller. Atlas will use its existing Unraid update schedule; Spark can request an idle replacement from Devices & storage or its container CLI. Actual replacement/rollback and final installation are still pending. [Update setup and boundaries](docs/updates.md).
