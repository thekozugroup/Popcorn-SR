# Verified Docker release kits

The [0.3.0 preview](https://github.com/thekozugroup/Popcorn-SR/releases/tag/v0.3.0) contains the simple input/queue workspace, large frame comparison and experimental native DLSS SR/frame generation worker. The older public GHCR image is still 0.2.0. A kit provides prebuilt manager and NGX worker images without requiring registry credentials or a build on your NAS. NVIDIA SDK libraries and AI weights are not included.

Download the kit matching the host and its `.sha256` file from the [GitHub releases](https://github.com/thekozugroup/Popcorn-SR/releases). Use AMD64 for an ordinary Unraid/x86 desktop and ARM64 for DGX Spark. Verify that one archive before extracting it. The release also supplies a combined SHA256SUMS, exact source commit and build/delivery evidence.

```sh
sha256sum --check popcorn-sr-0.3.0-linux-amd64.tar.gz.sha256
tar -xzf popcorn-sr-0.3.0-linux-amd64.tar.gz
cd popcorn-sr-0.3.0-linux-amd64
./load.sh manager
```

Use `./load.sh ngx` on the NVIDIA worker or `./load.sh all` on a single host. The loader checks the kit's file hashes, host architecture, immutable image revision and filesystem layers. It refuses to replace an existing different image with the same version tag. It only loads the selected images: it does not start services, create media/state/scratch folders, mount drives or change configuration. Images consume space in Docker's own data store.

Copy `.env.example` to a private `.env`, fill in the actual paths/access key/UID/GID, then append the image selections:

```sh
cat images.env >> .env
docker compose up -d --no-build --pull never manager
```

Existing users should add or update only the two image variables in their private `.env`; preserve state, library, output and worker credentials. With release-kit images use `--pull never`. The default registry image in the ordinary Compose files deliberately continues to identify the published 0.2.0 image, while `POPCORN_IMAGE` selects the loaded current manager/base worker. `POPCORN_NGX_IMAGE` selects the loaded native worker. The kit supplies both values.

For a paired NVIDIA worker use `compose.worker.yaml` + `compose.ngx.yaml`; for a single host use `compose.yaml` + `compose.single.yaml` + `compose.ngx.yaml`. Follow [deployment](deployment.md) to mark the mounted scratch subfolder and create the one-use pairing code. Provision the separately licensed runtime and native bridges according to [native setup](../native/README.md), then start with `--no-build --pull never`. Real startup renders control which enhancement settings become available. A missing runtime keeps that feature unavailable.

On Unraid without Compose, load the AMD64 manager image first and use its exact image name in a local Docker template or `docker run` configuration following [deployment](deployment.md). The existing registry template remains pinned to the older published image. This kit does not install or modify NAS templates automatically. Current kit acceptance does not establish Unraid Docker Manager's own update/pull behavior for local images.

The optional Real-ESRGAN AI worker remains a separate source build (`Dockerfile.ai`, `compose.ai.yaml`). Its CUDA dependencies are much larger; download the verified official model to the selected scratch drive. The exact 0.3.0 ARM64 AI image passed short Spark CUDA/NVENC film trials; both architectures passed locked builds/import checks. Current DLSS/AI exports can lose SDR color signaling, and video adaptation can change detail. Film quality, external-drive mount dependencies, player compatibility and your hardware still need a short preview before a library batch. See the release's acceptance receipt for exact source/artifacts and limits.

## Local packaging

From a clean committed checkout and an isolated Docker builder:

```sh
uv run python scripts/package-release.py --output evidence/release-candidate
```

The command builds both architectures, exports revision/architecture/hash descriptors, assembles checksum manifests, removes only its newly built version tags, reloads the actual distributable, compares imported identity and performs real CPU manager/NGX-worker delivery plus frame/full and 4K memory checks. ARM64 on an ARM64 host executes the kit loader directly; an emulated AMD64 image is reimported and exercised without claiming native x86 or GPU execution. `--include-ai` additionally builds both AI images and checks their locked imports; it does not imply CUDA processing.

Publish only passed artifacts and evidence from the same committed source. GitHub Actions are not required. Uploading a container to GHCR requires a separate account credential with package-upload permission; publishing GitHub release files uses repository permissions. Never place credentials in a kit, image or public receipt.
