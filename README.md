# Popcorn SR

**Your library stays on the NAS. The heavy lifting goes where you have the power.**

Popcorn Super Resolution is a self-hosted video manager and processing worker. Pair an Unraid NAS with a DGX Spark or NVIDIA Linux desktop, or run both services on one computer. Finished copies return to a chosen output folder. Originals remain untouched.

## What works in the 0.2.0 preview

- Lightweight authenticated web manager, persistent SQLite queue, one-use worker pairing.
- Network transfers with SHA-256 checks, worker leases, cancel/retry and validated output.
- H.264, HEVC and AV1 when the worker passes a real encoder check; CPU or NVIDIA NVENC.
- Conventional Lanczos resizing, noise reduction, deinterlacing, light sharpening and 60 fps motion interpolation.
- Optional Real-ESRGAN AI restoration on CUDA, with bounded tiles and an official verified checkpoint.
- Optional NVIDIA RTX Video Super Resolution through separately installed VFX on Linux x86.
- Experimental DLSS Super Resolution and DLSS 5 adapter contract; requires a separately installed, working video CLI. **No built-in Linux DLSS renderer ships in this release.**
- Short preview jobs, separate output folders, configurable scratch drive, single-host and paired Docker configurations.
- Matroska copies with original audio, subtitles, attachments, metadata and chapters; rejects missing streams or wrong duration/size/codec.

**Tested on a physical DGX Spark.** GB10 passed H.264/HEVC/AV1 NVIDIA encoding checks and completed separate two-computer resizing and Real-ESRGAN CUDA/NVENC jobs with intact sources and retained audio. These were short generated SDR clips in an existing CUDA runtime, not a whole-library benchmark or validation of the optional AI image. RTX 5080 and external Optane testing remain pending. GPU codecs and AI engines stay disabled until a real startup smoke check passes. Assess quality and speed on your own previews. HDR and high-bit-depth sources are rejected in this release to prevent destructive color/precision loss.

## Completion goal

Development remains active. Full completion requires **DLSS neural rendering, DLSS Super Resolution, RTX Video Super Resolution, RTX Video HDR and DLSS frame generation**, with real processing, usable controls, previews and compatible combinations. [Acceptance and current gaps](docs/nvidia-parity.md). The preview features below do not establish five-stage parity.

Development `main` now has an experimental native Linux CUDA DLSS Super Resolution video backend. Physical Spark tests passed all five SR modes, preset hints, three motion settings and H.264/H.265/AV1 video encoding with preserved frame timestamps. The dedicated NGX Docker worker also returned paired previews in all three codecs with audio and intact originals. It needs separately provisioned NVIDIA components and is **not in the published 0.2.0 image**. [Setup and evidence](native/README.md). Representative quality, NAS delivery and the other NVIDIA stages remain unfinished.

## Start on your NAS

1. Copy `.env.example` to `.env`. Set existing library, output and state directories. Generate a random key with `openssl rand -hex 32`; put it in `POPCORN_ADMIN_TOKEN`.
2. Run `docker compose up -d --no-build --pull always manager`.
3. Open `http://YOUR-NAS:8787`, sign in with your key, and choose **Processing → Connect a worker**.
4. On the processing computer, configure `compose.worker.yaml`, mount and initialize its scratch drive, and enter the pairing code.
5. Choose a video and run a five-second preview before processing the full file.

Use `PUID=99` and `PGID=100` for the usual Unraid share ownership. [Detailed installation](docs/deployment.md) includes the Unraid template, external Optane drive, single-host RTX desktop, native Linux AI runtime and Docker AI worker.

## Connections

Ethernet through a router/switch works. Direct Ethernet works with reachable static IP addresses. 1 GbE is usable; 10 GbE shortens large transfers when both ports support it. Wi-Fi is supported, but interrupted connections stop the job safely and may require retry. A plain USB-C cable between normal host ports does not establish a network. Attach an Optane enclosure to USB-C as storage instead. [Networking and drive guide](docs/hardware.md).

## Engines and compatibility

| Engine | Linux x86 desktop | Linux ARM64 / Spark | Bundled? |
|---|---|---|---|
| FFmpeg resizing + encoding | Runtime-tested | Runtime-tested | Yes |
| Real-ESRGAN AI | Compatible CUDA PyTorch required | Spark-compatible CUDA PyTorch required | Adapter/network code; model installed separately |
| RTX Video / NVIDIA VFX | Separate SDK; runtime-tested | Current public Python wheels lack Linux ARM64 | Adapter only |
| DLSS Super Resolution (4 / 4.5 runtime) | External video adapter; experimental | No verified ARM64 video backend | No renderer |
| DLSS 5 neural rendering | External video adapter; experimental | No verified ARM64 video backend | No renderer |
| Windows CLI engines | Future-focused adapters included | N/A | User installs engine |

DLSS 5 is appearance-changing neural rendering, distinct from restoration/upscaling. GPU memory capacity does not determine codec or SDK support. Every engine needs working drivers, APIs and architecture-compatible runtime. [Engine integration](docs/engines.md).

## Development

```sh
uv sync --extra dev
npm ci
npm run build
uv run ruff check .
uv run pytest
npx playwright install chromium
npm run test:browser
docker build -t popcorn-sr:dev .
uv run python scripts/docker-smoke.py
```

The web UI uses the official [Astryx](https://astryx.atmeta.com/) React components, a compiled zinc/blue theme, and system fonts. Vite builds static assets into the Python package and Docker image. There is no runtime Node server or CDN dependency. Rebuild with `npm run build` after changing the UI. The manager uses FastAPI and SQLite; workers use FFmpeg and optional independently installed GPU engines. [Architecture](docs/architecture.md) and [current verification](working.md).

## License and credits

Popcorn SR is AGPL-3.0-or-later. NVIDIA SDKs, models, containers and third-party engines retain their own terms; no proprietary engine binaries are vendored. BasicSR network code and Real-ESRGAN model attribution are recorded in [third-party notices](THIRD-PARTY-NOTICES.md). [fast-rtxvsr](https://github.com/glarsson/fast-rtxvsr) and [Visual Enhancer](https://github.com/Merserk/dlss5-visual-enhancer) informed the engine interface; Visual Enhancer is separately licensed and not redistributed. Design uses [Taste](https://tasteskill.dev) and [Impeccable](https://impeccable.style).
