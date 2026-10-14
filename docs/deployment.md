# Installation

For prebuilt manager/native-worker archives and current registry tags, follow [Docker release kits](releases.md). Kit images use explicit local selections and `--pull never`. [Container updates](updates.md) describes Unraid’s existing update path and the optional Linux host controller installed with 0.4.1.

The manager needs no GPU. A worker needs FFmpeg and a usable encoder. Network workers download from the manager and return results; they do not need an SMB/NFS share or an inbound port.

## Unraid manager

Use `unraid/popcorn-sr.xml` as a local Docker template. The CPU-only custom Unraid build can manage the library while the Spark does processing. Compose is optional and is not present on every Unraid installation.

Without Compose, save the XML under Unraid's user-template directory (`/boot/config/plugins/dockerMan/templates-user/`), then use **Docker → Add Container** and select the Popcorn SR template. Set the library, output and state paths, access key and port in that form. The library mount stays read-only. Apply the template and open the container's Web UI. Create the chosen state/output folders first and use UID 99/GID 100 for ordinary Unraid share ownership. This is an installation step for the operator; acceptance tests must not change existing user templates or services.

If Compose is already installed, use the alternative below:

1. Create separate host folders for app data and finished copies. Keep the library separate. Example: `/mnt/user/appdata/popcorn-sr`, `/mnt/user/popcorn-output`, `/mnt/user/media`.
2. Copy `.env.example` to `.env`, set those paths and `PUID=99`, `PGID=100`. They must exist and be writable by that user, except the read-only library.
3. Generate a key: `openssl rand -hex 32`. Put it in `.env` as `POPCORN_ADMIN_TOKEN`. Keep `.env` private and out of version control.
4. Run `docker compose up -d --no-build --pull always manager` from this checkout. Open `http://NAS-IP:8787`.
5. Sign in, then select **Devices & storage → Connect a worker**. The code expires in ten minutes; it is not your permanent access key.

The template uses the public `ghcr.io/thekozugroup/popcorn-sr:stable` image. Anonymous pulls need no GitHub account. Source builds remain available with `docker build -t popcorn-sr:dev .`. Do not expose port 8787 directly to the internet. Use a reverse proxy with HTTPS or a VPN for remote use; HTTP on a trusted LAN sends credentials/video without encryption.

## Linux worker on DGX Spark or RTX 5080 desktop

Install Docker, the current NVIDIA driver and [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). Verify GPU access with NVIDIA's documented container test. GPU passthrough on Docker Desktop for macOS is not supported by this app.

Clone this repository on the worker. Set these values in its own `.env`:

```dotenv
POPCORN_MANAGER=http://NAS-IP:8787
POPCORN_PAIR_CODE=code-from-the-web-interface
POPCORN_WORKER_NAME=DGX Spark
WORKER_STATE_PATH=/home/your-user/popcorn-worker-state
SCRATCH_PATH=/mnt/optane/popcorn-scratch
PUID=1000
PGID=1000
```

Use the worker user's actual numeric UID/GID. Create the state directory. Mount your external drive, then create a scratch subfolder **on that mounted drive**. Initialize it:

```sh
docker pull ghcr.io/thekozugroup/popcorn-sr:stable
docker run --rm --user "$(id -u):$(id -g)" \
  --mount type=bind,src=/mnt/optane/popcorn-scratch,dst=/scratch \
  ghcr.io/thekozugroup/popcorn-sr:stable init-scratch /scratch
docker compose -f compose.worker.yaml -f compose.nvidia.yaml up -d --no-build --pull always
```

The marker identifies the scratch folder and filesystem; worker state retains that identity across restarts. A missing or replaced filesystem stops processing. Graceful shutdown terminates processing; restart recovery removes only this worker’s marked jobs after their active child locks are released. Docker Compose refuses to create a missing host folder, and the worker refuses to run without the marker. The marker is not proof that the parent is a real mount: configure the host's mount/service dependencies too. After successful pairing, clear `POPCORN_PAIR_CODE` from `.env` and recreate the worker. Its small credential file survives in `WORKER_STATE_PATH`.

To exercise these controls locally with an already built manager/CPU image, run `uv run python scripts/docker-lifecycle.py --image popcorn-sr:dev`. The check uses generated clips, private temporary folders, unique Compose projects and a loopback port. It starts both the single-host layout and separate manager/worker projects using the shipped files. Active shutdown/crash and missing-drive fault injection run on the single-host CPU layout; unrelated temporary-drive files must survive. The check also tries a copied marker on a real disposable tmpfs filesystem. Its test lease is 16 seconds; the production default remains 90. It removes only its own containers, networks and temporary files and retains a new receipt under `evidence/`. It does not pull or remove the supplied image. This is local deployment evidence; actual GPU, LAN and external-drive acceptance remain separate.

The worker tests each codec with a real encode before appearing ready. Spark and desktop driver/library differences may disable individual codecs; no NVIDIA fallback to CPU occurs when a GPU job is requested.

In 0.4.0, pairing is saved before these tests start. The device immediately shows **Checking support**, stays connected while checks run, and accepts jobs only after verified options appear. Long GPU checks do not consume the code's remaining lifetime. **Checks failed** explains when to reconnect the temporary drive or restart the worker. Revoked pairing requires a new code and worker state folder.

In 0.4.0, select one or more videos in **Input**. In **Compare a frame**, choose the video and time, then **Preview frame**. Review the large Original/Enhanced images, or choose **Expand preview**. **Run full video** / **Run full batch** becomes available after both images load. The selected batch uses the current reviewed settings; the text identifies which video was sampled. Changes to the frame or settings require a new comparison. **Compare frame** in the queue reopens saved settings.

Still previews use a video-only sample of up to five seconds, starting at the chosen time. Only its first picture is compared, so generated intermediate frames and motion artifacts need the downloadable sample. HDR still comparisons are disabled: use **Preview 5 seconds**, download the HDR video and review it on an HDR display. These audiovisual previews retain **Enhance full video** in the queue. Full continuation reuses the saved source, destination, enhancement and device choice, resets the frame/time limit, rechecks source integrity/worker compatibility and restores full media preservation. A changed source requires a new preview. The worker currently downloads and verifies the whole source even for a short sample; allow enough scratch space and transfer time.

## Add open-source AI on Spark or desktop

The larger AI image uses pinned PyTorch CUDA 13.0 wheels on Python 3.12 and targets Linux AMD64 and ARM64. Its verified ARM64 development package passed short actual Unraid → Spark → Unraid Real-ESRGAN CUDA/NVENC previews in H.264/H.265/AV1 and full H.264 continuation, including preserved chapters/media bytes and intact originals. Local build/import checks also passed. This is functional short-clip acceptance; representative quality, long jobs, external-drive behavior and deferred RTX 5080 testing remain open. The optional AI image can be built from the release source. [Evidence and exact package provenance](../working.md).

Download the official model onto the initialized scratch drive:

```sh
python3 scripts/fetch-model.py /mnt/optane/popcorn-scratch
docker compose -f compose.worker.yaml -f compose.ai.yaml up -d --build
```

The AI worker image is substantially larger than the base worker; check the built image size when planning storage. Docker image layers live in the host's Docker data directory, so move that directory to the external drive too if you want to avoid built-in disk writes. AI model/inference smoke tests happen during startup and can take several minutes. Choose **Real-ESRGAN AI upscaling** only after it appears on the worker. Preview for flicker or changed detail. This is frame-based AI restoration, not temporal NVIDIA RTX VSR.

RTX Video uses a separate VFX runtime on Linux x86. See [engines](engines.md); no current public Linux ARM64 VFX Python wheel was found.

For the experimental native DLSS worker, use Docker Compose 2.30+ and follow [native setup](../native/README.md). Its NGX overlay includes a 384-MiB executable RAM temporary mount required for NVIDIA feature loading, with read-only SDK/driver mounts. Video intermediates still go to the selected temporary drive.

## One Linux desktop

Use `compose.yaml` with `compose.single.yaml`. Set manager paths and worker scratch/state paths in one `.env`.

```sh
docker compose up -d --no-build --pull always manager
```

Create a pairing code in the web interface, add it to `.env`, then run:

```sh
docker compose -f compose.yaml -f compose.single.yaml -f compose.nvidia.yaml up -d --no-build --pull always
```

For AI, download the model first, then build the larger local worker image:

```sh
docker compose -f compose.yaml -f compose.single.yaml -f compose.ai.yaml up -d --build
```

The AI image is a local build recipe; it is not published to a registry. Use this build command instead of the prebuilt worker's pull command. The internal manager address is `http://manager:8787` and does not depend on your LAN IP.

## Native Linux worker

This is useful with an existing Spark-compatible PyTorch runtime. Install Popcorn SR into that environment without replacing its CUDA PyTorch:

```sh
python3 -m pip install . 'av>=14,<18' 'numpy>=2,<3'
popcorn-sr init-scratch /mnt/optane/popcorn-scratch
python3 scripts/fetch-model.py /mnt/optane/popcorn-scratch
export POPCORN_ESRGAN_MODEL=/mnt/optane/popcorn-scratch/models/RealESRGAN_x4plus.pth
export POPCORN_PAIR_CODE=your-one-use-pairing-code
popcorn-sr worker --manager http://NAS-IP:8787 \
  --scratch /mnt/optane/popcorn-scratch --state /home/your-user/popcorn-worker-state
```

For persistent operation, use a systemd service with `RequiresMountsFor=/mnt/optane`, a private environment file and an unprivileged user. Put Python package caches, CUDA caches, logs and swap on the chosen drive too if endurance is the priority. Windows work is secondary; [engine adapters](engines.md) document separately installed Windows CLIs.

## Updates and recovery

Stop the manager before backing up its state directory (including SQLite WAL files). Keep output/media separate. Rebuild from a tagged checkout and preserve state mounts. Workers retain pairing unless revoked. A worker lease expires after a disconnect and the job becomes failed; review and retry rather than silently rerunning. Interrupted outputs are never published as finished files. A hard process/host crash can leave hidden `.partial.mkv` files and worker `job-*` folders; inspect/remove those only after stopping the affected service and confirming the job is inactive. They are never originals.

## Development device packages

Build on your development machine, then transfer a verified archive to the NAS or worker. This avoids compiling on either device. Run `uv run python scripts/verify-local.py` first, commit the intended runtime source, and build/export for the target architecture:

```sh
# Example: ARM64 worker. Use linux/amd64 and --architecture amd64 for Unraid.
docker build --platform linux/arm64 \
  --label "org.opencontainers.image.revision=$(git rev-parse HEAD)" \
  -f Dockerfile.ngx -t popcorn-sr-ngx:device .
uv run python scripts/export-device-package.py --image popcorn-sr-ngx:device \
  --architecture arm64 --output evidence/device-package-arm64/ngx
```

Use `Dockerfile` for the manager, or `Dockerfile.ai` for the locked Real-ESRGAN CUDA worker, with distinct tags/output directories. Docker needs emulation when the build machine and target architectures differ; a native build is preferable. Each export records archive SHA-256, source commit/file hashes, filesystem layers and environment. The exporter rejects uncommitted runtime changes or a mismatched image revision/platform. Build/import success without a GPU does not verify CUDA or NVIDIA features; perform isolated device acceptance before using a library. These are development packages, separate from the public release image.

The manual **Build device packages** and **Build AI device packages** workflows remain optional fallbacks if a local builder cannot support the required platform. They run full verification before building native AMD64/ARM64 archives. Routine development uses local commands; no workflow runs automatically on pushes or tags.

Check each archive against `package.json` before importing it. The `org.opencontainers.image.revision` label must match the intended commit. Docker can convert configuration IDs during archive import; compare filesystem layers, architecture and environment rather than assuming daemon image IDs will be identical. Use a dedicated test tag and remove only test resources you created. NVIDIA components are provisioned separately; an NGX package build/import does not establish GPU processing or feature availability.
