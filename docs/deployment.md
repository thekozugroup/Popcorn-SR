# Installation

The manager needs no GPU. A worker needs FFmpeg and a usable encoder. Network workers download from the manager and return results; they do not need an SMB/NFS share or an inbound port.

## Unraid manager

Use `unraid/popcorn-sr.xml` as a local Docker template, or run Compose. The CPU-only custom Unraid build can manage the library while the Spark does processing.

1. Create separate host folders for app data and finished copies. Keep the library separate. Example: `/mnt/user/appdata/popcorn-sr`, `/mnt/user/popcorn-output`, `/mnt/user/media`.
2. Copy `.env.example` to `.env`, set those paths and `PUID=99`, `PGID=100`. They must exist and be writable by that user, except the read-only library.
3. Generate a key: `openssl rand -hex 32`. Put it in `.env` as `POPCORN_ADMIN_TOKEN`. Keep `.env` private and out of version control.
4. Run `docker compose up -d --build manager` from this checkout. Open `http://NAS-IP:8787`.
5. Sign in, then select **Processing → Connect a worker**. The code expires in ten minutes; it is not your permanent access key.

The template uses `ghcr.io/thekozugroup/popcorn-sr:0.1.0`, published by the release workflow. Before that tag is available, build locally with `docker build -t popcorn-sr:0.1.0 .` and select that local image in Unraid. Do not expose port 8787 directly to the internet. Use a reverse proxy with HTTPS or a VPN for remote use; HTTP on a trusted LAN sends credentials/video without encryption.

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
docker build -t popcorn-sr:0.1.0 .
docker run --rm --user "$(id -u):$(id -g)" \
  --mount type=bind,src=/mnt/optane/popcorn-scratch,dst=/scratch \
  popcorn-sr:0.1.0 init-scratch /scratch
docker compose -f compose.worker.yaml -f compose.nvidia.yaml up -d --build
```

The marker identifies the scratch folder. Docker Compose refuses to create a missing host folder, and the worker refuses to run without the marker. The marker is not proof that the parent is a real mount: configure the host's mount/service dependencies too. After successful pairing, clear `POPCORN_PAIR_CODE` from `.env` and recreate the worker. Its small credential file survives in `WORKER_STATE_PATH`.

The worker tests each codec with a real encode before appearing ready. Spark and desktop driver/library differences may disable individual codecs; no NVIDIA fallback to CPU occurs when a GPU job is requested.

## Add open-source AI on Spark or desktop

The larger AI image uses NVIDIA's CUDA PyTorch base. This path is intended for both Linux AMD64 and ARM64; **physical GPU validation is pending**. Base image availability and GPU support must be checked on the target device.

Download the official model onto the initialized scratch drive:

```sh
python3 scripts/fetch-model.py /mnt/optane/popcorn-scratch
docker compose -f compose.worker.yaml -f compose.ai.yaml up -d --build
```

The NVIDIA base is several GB. Docker image layers live in the host's Docker data directory, so move that directory to the external drive too if you want to avoid built-in disk writes. AI model/inference smoke tests happen during startup; pairing can take several minutes. Choose **Real-ESRGAN AI upscaling** only after it appears on the worker. Preview for flicker or changed detail. This is frame-based AI restoration, not temporal NVIDIA RTX VSR.

RTX Video uses a separate VFX runtime on Linux x86. See [engines](engines.md); no current public Linux ARM64 VFX Python wheel was found.

## One Linux desktop

Use `compose.yaml` with `compose.single.yaml`. Set manager paths and worker scratch/state paths in one `.env`.

```sh
docker compose up -d --build manager
```

Create a pairing code in the web interface, add it to `.env`, then run:

```sh
docker compose -f compose.yaml -f compose.single.yaml -f compose.nvidia.yaml up -d --build
```

For AI, use `compose.ai.yaml` in place of `compose.nvidia.yaml` after downloading the model. The internal manager address is `http://manager:8787` and does not depend on your LAN IP.

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
