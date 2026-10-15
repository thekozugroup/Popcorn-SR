# Releases

Manager and optional restoration worker **0.5.0** add FlashVSR+ Turbo and caption-preserving MOV/MP4 output. Public AMD64/ARM64 channels are `ghcr.io/thekozugroup/popcorn-sr:stable` and `:restoration-stable`, with versioned `:0.5.0` and `:restoration-0.5.0` tags. Pinned model weights are installed separately; the native-only `ngx-stable` channel stays at 0.4.1. [Restoration setup and measured limits](video-restoration.md). No new offline kit or proprietary runtime is bundled.

Exact runtime `ec43942070277b20f48ab044819d69ea56d50cc6` passes 213 Mac/Linux Python cases, 17 browser workflows, 22 Compose layouts and both platform Docker delivery checks. Spark's final packaged ALF test rendered 149 pictures to 1440×1080 HEVC in 140.20 seconds. Installed paired previews, original audio/caption packet preservation, linked comparison, existing-feature retention and container-initiated current-version checks pass. Tests were local; AMD64 execution was emulated and no physical RTX 5080 or full episode was tested. [Release evidence](https://github.com/thekozugroup/Popcorn-SR/releases/download/v0.5.0/acceptance.json).

Prior manager **0.4.4** adds linked Original/Enhanced zoom up to 8×, panning from either image, Fit reset, keyboard/touch controls and retained resize/fullscreen views. **Delete preview** removes a terminal sample and its queue entry while preserving originals and full outputs. The AMD64/ARM64 image `ghcr.io/thekozugroup/popcorn-sr:0.4.4` and `stable` passed 182 Mac tests, 182 packaged-Linux tests, 16 browser workflows, 18 Compose layouts and paired Docker delivery/deletion on both platforms. Installed Atlas/Spark native processing, linked letterboxed views, preview deletion and accessibility checks passed. Atlas keeps its native Unraid updater, account/passkeys, pairing, read-only mounts and user jobs. Owned device test files and local publishing resources are removed. Native DLSS worker **0.4.1** remains unchanged on `ngx-stable`. Generated clips establish functionality, not movie quality or throughput. [Release evidence](https://github.com/thekozugroup/Popcorn-SR/releases/download/v0.4.4/acceptance.json). No replacement offline kit or new NVIDIA runtime is included.

Prior manager **0.4.3** adds a read-only library selector, folder filtering, breadcrumbs and selections across folders/libraries. The optional Jellyfin overlay mounts existing movie/show folders while retaining original test-library paths, account/passkeys, jobs and worker pairing. Results stay in a separate output mount. [Library setup](library.md). The versioned AMD64/ARM64 image `ghcr.io/thekozugroup/popcorn-sr:0.4.3` was published after local, packaged Linux, paired Docker and installed Unraid acceptance. [Release evidence](https://github.com/thekozugroup/Popcorn-SR/releases/download/v0.4.3/acceptance.json).

Prior manager 0.4.2 adds owner login, mandatory replacement of the initial **admin / admin** password and optional passkeys. It is compatible with the accepted native worker 0.4.1. The versioned manager image `ghcr.io/thekozugroup/popcorn-sr:0.4.2` was published for AMD64/ARM64 after local and installed acceptance; `stable` now receives 0.5.0. This release uses registry images; no replacement archive kit is published. Follow [login setup](deployment.md#login-and-passkeys) for HTTPS and recovery. The archive instructions below describe the prior 0.4.1 kit, which retains its earlier access-key login.

## Prior verified Docker release kits

The published [0.4.1 release](https://github.com/thekozugroup/Popcorn-SR/releases/tag/v0.4.1) contains the simple input/queue workspace, large frame comparison, per-resolution rules and experimental native DLSS SR/frame generation worker. The multi-architecture registry supplies `ghcr.io/thekozugroup/popcorn-sr:0.4.1` and `ghcr.io/thekozugroup/popcorn-sr:ngx-0.4.1`; `ngx-stable` identifies this native worker; `stable` also receives compatible manager updates. Both kits passed import/delivery checks, and the installed Unraid/Spark pair passed genuine GPU returns. Full anonymous archive checks and anonymous registry pulls verify public distribution. A kit provides prebuilt images without requiring registry credentials or a build on your NAS. NVIDIA SDK libraries and AI weights are not included.

Download the kit matching the host and its `.sha256` file from the [GitHub releases](https://github.com/thekozugroup/Popcorn-SR/releases). Use AMD64 for an ordinary Unraid/x86 desktop and ARM64 for DGX Spark. Verify that one archive before extracting it. The release also supplies a combined SHA256SUMS, exact source commit and build/delivery evidence.

```sh
sha256sum --check popcorn-sr-0.4.1-linux-amd64.tar.gz.sha256
tar -xzf popcorn-sr-0.4.1-linux-amd64.tar.gz
cd popcorn-sr-0.4.1-linux-amd64
./load.sh manager
```

Use `./load.sh ngx` on the NVIDIA worker or `./load.sh all` on a single host. The loader checks the kit's file hashes, host architecture, immutable image revision and filesystem layers. It refuses to replace an existing different image with the same version tag. It only loads the selected images: it does not start services, create media/state/scratch folders, mount drives or change configuration. Images consume space in Docker's own data store.

Copy `.env.example` to a private `.env`, fill in the actual paths/UID/GID and the legacy access key required by that older kit, then append the image selections:

```sh
cat images.env >> .env
docker compose up -d --no-build --pull never manager
```

Existing users should add or update only the two image variables in their private `.env`; preserve state, library, output and worker credentials. With release-kit images use `--pull never`. The ordinary Compose files use the verified `stable` channel, while `POPCORN_IMAGE` selects the loaded current manager/base worker. `POPCORN_NGX_IMAGE` selects the loaded native worker. The kit supplies both values. It also includes the optional worker-update overlay, host controller and systemd units; follow [updates](updates.md). Local image-only installs receive no registry updates until configured for a published channel.

For a paired NVIDIA worker use `compose.worker.yaml` + `compose.ngx.yaml`; for a single host use `compose.yaml` + `compose.single.yaml` + `compose.ngx.yaml`. Follow [deployment](deployment.md) to mark the mounted scratch subfolder and create the one-use pairing code. Provision the separately licensed runtime and native bridges according to [native setup](../native/README.md), then start with `--no-build --pull never`. Real startup renders control which enhancement settings become available. A missing runtime keeps that feature unavailable.

On Unraid without Compose, load the AMD64 manager image first and use its exact image name in a local Docker template or `docker run` configuration following [deployment](deployment.md). The supplied Unraid template uses the verified `stable` channel. This kit does not install or modify NAS templates automatically. Atlas was separately installed through its native template and anonymous registry pull, preserving saved pairing and existing services; its existing updater now includes Popcorn-SR. Locally loaded kit tags still require explicit operator updates.

The optional Real-ESRGAN AI worker remains a separate source build (`Dockerfile.ai`, `compose.ai.yaml`). Its CUDA dependencies are much larger; download the verified official model to the selected scratch drive. The exact 0.3.1 ARM64 AI image passed short Spark CUDA/NVENC film trials; both architectures passed locked builds/import checks. Current 0.3.1 DLSS/AI color trials retain known BT.709/BT.601 range and signaling across all three codecs. Unknown labels are not guessed; unsupported/conflicting profiles fail. Video adaptation can change detail. Film quality, external-drive mount dependencies, player compatibility and your hardware still need a short preview before a library batch. See the release's acceptance receipt for exact source/artifacts and limits.

## Local packaging

From a clean committed checkout and an isolated Docker builder:

```sh
uv run python scripts/package-release.py --output evidence/release-candidate
```

The command builds both architectures, exports revision/architecture/hash descriptors, assembles checksum manifests, removes only its newly built version tags, reloads the actual distributable, compares imported identity and performs real CPU manager/NGX-worker delivery plus frame/full and 4K memory checks. ARM64 on an ARM64 host executes the kit loader directly; an emulated AMD64 image is reimported and exercised without claiming native x86 or GPU execution. `--include-ai` additionally builds both AI images and checks their locked imports; it does not imply CUDA processing.

Publish only passed artifacts and evidence from the same committed source. GitHub Actions are not required. Uploading a container to GHCR requires a separate account credential with package-upload permission; publishing GitHub release files uses repository permissions. Never place credentials in a kit, image or public receipt.
