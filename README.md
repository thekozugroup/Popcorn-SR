# Popcorn SR

<img src="web/public/popcorn-sr.png" alt="Popcorn SR app icon" width="96" height="96">

**Keep your library on the NAS. Process videos on the computer with the power.**

Popcorn Super Resolution runs as a lightweight Docker manager plus a processing worker. Pair an Unraid NAS with a DGX Spark or NVIDIA Linux desktop, or run both services on one computer. Finished copies return to your chosen output folder. Originals remain untouched.

## Preview before a batch

The workspace puts input on the left, the output queue on the right and settings underneath. Select a video or batch, choose a video and time, then **Preview frame**. Compare large Original/Enhanced images or **Expand preview**. **Zoom in** enlarges both images together; drag either image to inspect the same detail. **Fit** resets the view. Double-click a detail or scroll while zoomed; keyboard arrows pan, +/− zoom and 0 resets. Magnification is relative to the fitted frame and does not change the output.

Choose **Light**, **Dark** or **System** appearance in the header; the choice is remembered by your browser and is also available before sign-in. The shared Popcorn family icon, locally bundled headings and layered zinc surfaces keep the same simple workspace in both themes.

Choose **Run full video** or **Run full batch** after reviewing. Changing the frame or processing settings requires a fresh comparison. Completed previews reopen from the queue. **Delete preview** removes that sample and its queue entry; originals and full-length copies remain. Finish or cancel an active preview first. Comparison PNGs are generated on demand rather than saved as extra files; deleting the preview also clears the displayed comparison.

Still comparisons process a video-only sample of up to five seconds, then display its first picture. Review the downloadable video sample for motion. Full runs restore the normal audio/subtitle/attachment/chapter checks and verify the saved source again.

## Install the published Docker preview

The current public manager is **0.5.1**, with the shared Popcorn family design, saved appearance choices, linked comparison zoom/panning, preview deletion, a read-only library picker, username/password login and optional passkeys. The optional **0.5.0 restoration worker** adds FlashVSR+; the native-only DLSS channel remains **0.4.1**. Docker selects the matching AMD64 or ARM64 image automatically; no build on the NAS is required.

1. Install the manager through the [Unraid template or Compose instructions](docs/deployment.md).
2. Set your existing library, output and state folders and ownership IDs.
3. Open the Web UI. Sign in with **admin / admin**, choose a new password, then add a passkey or choose **Not now**. Choose **Devices & storage → Connect a worker**.
4. On the processing computer, configure and initialize its mounted scratch folder, then pair with the one-use code.
5. Preview one frame or a short sample before running a batch.

Use UID/GID **99/100** for ordinary Unraid share ownership. The public registry supplies `ghcr.io/thekozugroup/popcorn-sr:0.5.0` on the `stable` channel and `ghcr.io/thekozugroup/popcorn-sr:ngx-0.4.1` on `ngx-stable`. Earlier [0.4.1 offline kits](docs/releases.md) remain available and retain their older access-key login; update the manager to use the new flow. [Detailed deployment](docs/deployment.md) includes manual Unraid installation, paired and single-host layouts.

## Choose Jellyfin videos

In **Input → Library**, choose your mounted movie/show folder, open a movie or show/season, and select videos. **Filter this folder** narrows names without scanning the whole library. Selections stay across folders; originals remain read-only and finished copies go to your separate output mount. Use [the library guide](docs/library.md) to add Jellyfin folders through Unraid or the optional `compose.library.yaml` overlay. No Jellyfin credentials or import copy is needed.

## Video restoration

[One-container Spark setup](docs/spark.md) uses a single published-image Compose file and the worker's built-in model installer. No model server, inference sidecar or host Python setup is needed. Models persist as ordinary application data across updates.

[Measured Spark bottlenecks and AI restoration](docs/video-restoration.md) compares SeedVR2, FlashVSR+, Real-ESRGAN and native DLSS on bounded ALF samples, with explicit RTX 5080/Linux limits. The optional `restoration-stable` worker runs FlashVSR+ Turbo after genuine CUDA/codec checks and a deliberate 7.0 GB model installation. It is installed on Spark alongside the existing DLSS support. A five-second ALF preview returned to the NAS in about 150 seconds; restoration is an optional video model, not a demonstrated speed upgrade over DLSS. Review matched frames and motion before a library batch.

## Processing options

Choose **H.264**, **H.265 / HEVC** or **AV1** independently of the enhancement. Upscaling changes frames; encoding compresses those frames into the finished copy. Most copies use Matroska (`.mkv`); preserving original MP4 timed text selects MP4, while EIA-608 captions select MOV with H.264/H.265. AV1 with EIA-608 is rejected before processing; video-only frame comparisons remain available. H.264 offers broad player compatibility; check HEVC/AV1 support on your players. Available codecs and enhancement controls require real worker processing checks.

Version 0.4.1 adds **Resolution rules** for mixed batches: for example, 720p→1080p and 1080p→4K. Each file keeps its aspect ratio; input rows show original dimensions/format, and output rows show final dimensions/format. Saved previews use the same rule for the full run. Both manager and worker must support the feature. [How resolution rules work](docs/resolution-rules.md).

| Option | Current support | Additional installation |
|---|---|---|
| Conventional resizing, noise reduction, deinterlacing and sharpening | CPU or NVIDIA encoding | FFmpeg is included |
| FlashVSR+ video restoration | Optional CUDA worker; packaged and paired Spark execution verified | Restoration image plus pinned read-only models; 8-bit SDR only |
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

Manager/restoration 0.5.0 at `ec43942070277b20f48ab044819d69ea56d50cc6` passes 213 Mac and packaged-Linux tests, 17 browser workflows, 22 Compose layouts and both manager-platform Docker checks, including actual audio/caption packet preservation and safe deletion. The physical Spark passed all existing native settings plus H.264/HEVC/AV1 FlashVSR+ and caption-copy checks. Paired ALF motion/frame returns, downloads and the real linked comparison passed. These short trials establish operation; full-episode stability, 4K restoration and RTX 5080/Linux speed remain unmeasured. [0.5.0 acceptance](https://github.com/thekozugroup/Popcorn-SR/releases/download/v0.5.0/acceptance.json).

Prior manager 0.4.4 at `3179bae3f6210dd39dd54fdeb9d152b7c3d59276` passes 182 Python tests on Mac and packaged Linux, all 16 Chromium workflows, 18 Compose layouts and both manager-platform paired Docker checks with a 0.4.1 worker. Linked picture coordinates, keyboard/touch controls and safe preview deletion pass; originals and full outputs remain intact. Installed Atlas/Spark DLSS processing, unequal-resolution letterboxed panning, resize/fullscreen/Fit, preview deletion and desktop/tablet/phone checks pass. Versioned/stable images and public receipt downloads match anonymously. Atlas preserves its owner/passkeys, pairing, existing and newly added jobs, mounts and native updater; temporary test files are removed. The native worker is unchanged. Generated clips verify operation, not film quality or throughput. [0.4.4 acceptance](https://github.com/thekozugroup/Popcorn-SR/releases/download/v0.4.4/acceptance.json).

Prior manager 0.4.3 at `d8535b9225586b933f87c525b0ca64b541a61d49` passes 171 Python tests on Mac and packaged Linux, all 14 Chromium workflows, 18 Compose layouts and both manager-platform paired Docker checks with a 0.4.1 worker. Named-source processing, blocked source writes, frame/full continuation, audio and 4K validation pass. Installed read-only movie/show browsing, original-frame reads, owner/pairing preservation and desktop/tablet/phone checks pass. [0.4.3 acceptance](https://github.com/thekozugroup/Popcorn-SR/releases/download/v0.4.3/acceptance.json).

Prior manager 0.4.2 was built from `ab557e46ef199d51c7a4eed909440439a2f0dfe5`. All 168 Python cases pass on Mac and Linux; the Linux QA overlay adds only the diagnostic `ps` tool. Twelve existing browser workflows and a genuine WebAuthn registration/sign-in workflow pass, including rejection of altered origins/signatures and replay. Both manager platforms pass real paired CPU delivery, frame/full continuation, audio preservation and concurrent 4K validation within 512 MiB. Compose restart/recovery passes; anonymous versioned and stable pulls match both committed filesystems. Installed HTTPS owner setup and desktop/tablet/phone UI checks pass while the accepted Spark worker stays running. A physical user passkey is created at first sign-in. [0.4.2 acceptance](https://github.com/thekozugroup/Popcorn-SR/releases/download/v0.4.2/acceptance.json).

The 0.4.1 release kits were built locally from `0e752f8704a8dac37a947d49110e70b7901d1a7d`, checksum-verified, reloaded and exercised through paired CPU delivery on native ARM64 and emulated AMD64. Verification includes selected-frame/full continuation, copied audio, intact originals and concurrent 4K frames within a 512-MiB manager limit. All 150 Python tests pass on Mac and Linux/FFmpeg 7, alongside twelve browser workflows, 17 Compose configurations, native syntax, UI build and dependency audit. The installed Unraid manager and Spark worker passed fresh 25 SR / nine FG / six-encoder startup checks, five paired returned samples/full copies across all three codecs, mapped 720p→1080p and 1080p→4K, and saved AV1 full continuation with original audio. Actual installed desktop/tablet/phone UI audits passed. Earlier 0.3.1 AI acceptance is separate; that optional image was not rebuilt for 0.4.1. These short trials establish processing and preservation, not whole-library quality or sustained throughput. [Public acceptance receipt](https://github.com/thekozugroup/Popcorn-SR/releases/download/v0.4.1/acceptance.json) · [Current work and exact evidence](working.md).

```sh
uv run python scripts/verify-local.py
```

Install `uv`, Node.js, FFmpeg, a C++17 compiler and Docker. Linux may also need Chromium's system dependencies. The command checks source, UI/browser flows, images and real Docker processing/lifecycle behavior; it writes an ignored receipt and uses unique image tags. `--software-only` is partial verification; `--include-ai` also builds the larger CUDA image. Actual GPU acceptance needs a device. [Local packaging](docs/releases.md#local-packaging).

GitHub workflows are manual fallbacks; pushes, PRs and version tags do not launch them. Current releases use local builds and GitHub release files.

The UI uses official [Astryx](https://astryx.atmeta.com/) React components, zinc surfaces, blue-500 actions and system fonts. Vite builds static assets served by the Python manager, with no Node server or CDN at runtime. Rebuild with `npm run build` after UI changes. [Architecture](docs/architecture.md) · [Rust assessment](docs/rust-assessment.md).

## License and family

Popcorn SR is AGPL-3.0-or-later. NVIDIA SDKs and third-party engines retain their own terms. [Third-party notices](THIRD-PARTY-NOTICES.md) record BasicSR, Real-ESRGAN, Astryx and brand attribution. [fast-rtxvsr](https://github.com/glarsson/fast-rtxvsr) and [Visual Enhancer](https://github.com/Merserk/dlss5-visual-enhancer) informed the engine interface; their separately licensed runtimes are not redistributed. Design uses [Taste](https://tasteskill.dev) and [Impeccable](https://impeccable.style).

SR uses [Popcorn Batch's three-circle mark](https://github.com/thekozugroup/Popcorn-Batch/blob/54170f2684f734712b6159ccc7592f3237fa6b71/web/src/app/icon.svg), highlighting the lower-right circle in Tailwind teal-500. Action colors stay blue. Rust remains a candidate for measured worker/frame-handling improvements; no rewrite or unmeasured speedup is claimed.

Atlas is installed on the public stable channel using its existing Unraid update schedule. Spark uses the optional restoration-channel host controller and can request an idle update from Devices & storage or its container CLI. Real CPU replacement/rollback, manual GPU replacement with fresh feature-retention checks, and the container-initiated public current-version check pass. Automatic published-version GPU replacement/rollback remains untested. Updates follow verified stable releases, rather than every source push. [Update setup and boundaries](docs/updates.md).
