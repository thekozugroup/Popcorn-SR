import asyncio
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import Settings, beneath
from .db import Store, digest
from .dlss import compatible_recipe
from .media import VIDEO_EXTENSIONS, dimensions, frame_image, inspect_source, probe, sha256, validate_output
from .models import Failure, Heartbeat, JobCreate, PairRequest


def create_app(settings: Settings | None = None):
    cfg = settings or Settings.from_env()
    store = Store(cfg.state)
    cfg.output.mkdir(parents=True, exist_ok=True)
    if cfg.library.resolve() == cfg.output.resolve() or cfg.output.resolve().is_relative_to(
        cfg.library.resolve()
    ):
        raise RuntimeError("Library and output must be separate folders. Mount originals read-only.")
    attempts = {}
    media_slots = asyncio.Semaphore(1)

    async def media_call(function, *args):
        # Frame requests and return validation share the lightweight manager's
        # decoder budget; simultaneous browser requests cannot multiply it.
        async with media_slots:
            task = asyncio.create_task(asyncio.to_thread(function, *args))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                await task
                raise

    @asynccontextmanager
    async def lifespan(app):
        async def reap():
            while True:
                with store.connect() as db:
                    store.expire(db)
                    db.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
                await asyncio.sleep(10)

        task = asyncio.create_task(reap())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    app = FastAPI(title="Popcorn SR", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.store, app.state.settings = store, cfg

    # Built UI policy permits only Astryx's exact static selector-placement sheet.
    policy_file = Path(__file__).parent / "static" / "ui-policy.json"
    style_hashes = []
    if policy_file.is_file():
        for value in json.loads(policy_file.read_text()).get("style_hashes", []):
            if re.fullmatch(r"sha256-[A-Za-z0-9+/]{43}=", value):
                style_hashes.append("'" + value + "'")
    style_sources = " ".join(["'self'", *style_hashes])

    @app.middleware("http")
    async def security(request, call_next):
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            if urlparse(origin).netloc != request.headers.get("host"):
                return Response("Cross-site requests are blocked.", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            f"default-src 'self'; style-src {style_sources}; script-src 'self'; img-src 'self' data:; media-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        if request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def bearer(request):
        auth = request.headers.get("authorization", "")
        return auth[7:] if auth.startswith("Bearer ") else ""

    def admin(request: Request):
        token = bearer(request)
        if token and secrets.compare_digest(token.encode(), cfg.admin_token.encode()):
            return
        session = request.cookies.get("popcorn_session", "")
        with store.connect() as db:
            row = db.execute(
                "SELECT 1 FROM sessions WHERE hash=? AND expires>?", (digest(session), time.time())
            ).fetchone()
        if not session or not row:
            raise HTTPException(401, "Sign in to manage your library.")

    def worker(request: Request):
        item = store.worker(bearer(request))
        if not item:
            raise HTTPException(401, "Worker is unpaired or revoked.")
        store.touch(item["id"])
        return item

    def owned(identity, item, lease):
        try:
            return store.owned(identity, item["id"], lease)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    def public_job(job):
        return {k: v for k, v in job.items() if k not in {"lease", "lease_until", "source"}} | {
            "source": {k: v for k, v in job["source"].items() if k != "mtime_ns"}
        }

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    class Login(BaseModel):
        token: str = Field(max_length=512)

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        address = request.client.host if request.client else "unknown"
        now = time.time()
        recent = [t for t in attempts.get(address, []) if t > now - 60]
        if len(recent) >= 10:
            raise HTTPException(429, "Too many attempts. Wait a minute and try again.")
        if not secrets.compare_digest(body.token.encode(), cfg.admin_token.encode()):
            attempts[address] = [*recent, now]
            raise HTTPException(401, "Access key is incorrect.")
        attempts.pop(address, None)
        token = secrets.token_urlsafe(32)
        with store.connect() as db:
            db.execute("INSERT INTO sessions VALUES (?,?)", (digest(token), now + 86400))
        response.set_cookie(
            "popcorn_session",
            token,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=86400,
        )
        return {"ok": True}

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        with store.connect() as db:
            db.execute(
                "DELETE FROM sessions WHERE hash=?", (digest(request.cookies.get("popcorn_session", "")),)
            )
        response.delete_cookie("popcorn_session")
        return {"ok": True}

    @app.get("/api/state", dependencies=[Depends(admin)])
    def state():
        with store.connect() as db:
            store.expire(db)
        return {
            "version": __version__,
            "workers": store.workers(),
            "jobs": [public_job(j) for j in store.jobs()],
            "storage": {
                "library": str(cfg.library),
                "output": str(cfg.output),
                "free_bytes": shutil.disk_usage(cfg.output).free,
            },
            "engine_notes": {
                "resize": "Lanczos resizing. Works without an AI runtime.",
                "realesrgan": "Open-source AI restoration. Per-frame processing can introduce temporal flicker; preview first.",
                "rtx-vsr": "AI upscaling through a separately installed RTX Video engine.",
                "dlss-sr": "Experimental video DLSS. Estimated motion and flat depth can affect detail; compare a preview.",
                "dlss5": "Experimental neural rendering. May change the appearance of the original.",
            },
        }

    @app.get("/api/library", dependencies=[Depends(admin)])
    def library(directory: str = ".", offset: int = 0):
        if offset < 0:
            raise HTTPException(400, "Invalid page.")
        try:
            folder = beneath(cfg.library, directory)
            if not folder.is_dir():
                raise ValueError("Folder does not exist. Check the library mount.")
            items = []
            for entry in folder.iterdir():
                if entry.is_symlink() or entry.name.startswith("."):
                    continue
                if entry.is_dir() or entry.suffix.lower() in VIDEO_EXTENSIONS:
                    items.append(
                        {
                            "name": entry.name,
                            "path": str(entry.relative_to(cfg.library)),
                            "directory": entry.is_dir(),
                            "size": 0 if entry.is_dir() else entry.stat().st_size,
                        }
                    )
            items.sort(key=lambda e: (not e["directory"], e["name"].casefold()))
            return {
                "directory": directory,
                "items": items[offset : offset + 100],
                "total": len(items),
                "offset": offset,
            }
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/pair-codes", dependencies=[Depends(admin)])
    def pair_code():
        return {"code": store.pair_code(), "expires_in": 600}

    @app.post("/api/workers/pair")
    def pair(body: PairRequest):
        if len(json.dumps(body.model_dump())) > 32768:
            raise HTTPException(400, "Worker description is too large.")
        try:
            return store.pair(body.code, body.name, body.capabilities, body.scratch)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/workers/{identity}/revoke", dependencies=[Depends(admin)])
    def revoke(identity: str):
        with store.connect() as db:
            db.execute("UPDATE workers SET revoked=1 WHERE id=?", (identity,))
            db.execute(
                "UPDATE jobs SET status='cancelled',stage='Worker revoked',lease=NULL WHERE worker_id=? AND status='running'",
                (identity,),
            )
        return {"ok": True}

    @app.post("/api/worker/status")
    async def worker_status(request: Request, item: Annotated[dict, Depends(worker)]):
        data = await request.json()
        if len(json.dumps(data)) > 32768:
            raise HTTPException(400, "Worker description is too large.")
        store.touch(item["id"], data.get("capabilities", {}), data.get("scratch", {}))
        updates = data.get("capabilities", {}).get("updates", {})
        acknowledged = updates.get("request_id") if isinstance(updates, dict) else None
        if isinstance(acknowledged, str):
            store.acknowledge_update(item["id"], acknowledged)
        return {"ok": True, "update_request": store.update_request(item["id"])}

    @app.post("/api/workers/{identity}/update", dependencies=[Depends(admin)])
    def update_worker(identity: str):
        item = next((w for w in store.workers() if w["id"] == identity and not w["revoked"]), None)
        if not item or not item["online"] or not item["capabilities"].get("updates", {}).get("enabled"):
            raise HTTPException(409, "Connect a worker with its host update service running.")
        return {"request_id": store.request_update(identity)}

    async def queue_job(body: JobCreate, expected_source=None, require_compatible=False):
        try:
            path = beneath(cfg.library, body.path, file=True)
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                raise ValueError("Choose a supported video file.")
            beneath(cfg.output, body.recipe.output_directory)
            if body.recipe.engine != "resize" and body.recipe.encoder != "nvidia":
                raise ValueError("AI engines require the NVIDIA encoding option.")
            if body.recipe.hdr:
                if body.recipe.encoder != "nvidia" or body.recipe.codec not in {"hevc", "av1"}:
                    raise ValueError("RTX Video HDR requires NVIDIA encoding with H.265 or AV1.")
                if body.recipe.engine not in {"resize", "dlss-sr", "rtx-vsr"}:
                    raise ValueError("This upscaler has no verified lossless HDR combination yet.")
            if body.recipe.frame_generation:
                if body.recipe.encoder != "nvidia":
                    raise ValueError("DLSS frame generation requires NVIDIA encoding.")
                if body.recipe.interpolate:
                    raise ValueError("Choose DLSS frame generation or conventional motion interpolation.")
                if body.recipe.engine not in {"resize", "dlss-sr", "rtx-vsr"}:
                    raise ValueError("This upscaler has no verified lossless frame-generation combination yet.")
            if body.recipe.engine != "resize" and any(
                [body.recipe.denoise, body.recipe.deinterlace, body.recipe.sharpen, body.recipe.interpolate]
            ):
                raise ValueError(
                    "Cleanup filters currently work with conventional resizing. Disable them for an AI engine."
                )
            if body.recipe.engine == "dlss5" and body.recipe.scale != 1:
                raise ValueError("DLSS 5 changes appearance at source size. Choose 1×.")
            if body.recipe.engine == "dlss-sr" and body.recipe.dlss_mode is None and body.recipe.scale not in {1, 2, 3}:
                raise ValueError("Video DLSS supports 1×, 2× or 3× in this adapter.")
            if body.worker_id and body.worker_id not in {
                w["id"] for w in store.workers() if not w["revoked"]
            }:
                raise ValueError("Choose an active worker.")
            advanced_dlss = body.recipe.engine == "dlss-sr" and (
                body.recipe.dlss_mode is not None or body.recipe.dlss_preset != "default"
                or body.recipe.temporal_quality != "high"
            )
            advanced_vsr = body.recipe.engine == "rtx-vsr" and any(value is not None for value in (
                body.recipe.vsr_quality, body.recipe.vsr_strength, body.recipe.output_width,
            ))
            if (require_compatible or advanced_dlss or advanced_vsr or body.recipe.frame_generation or body.recipe.hdr) and not any(
                not w["revoked"]
                and (not body.worker_id or w["id"] == body.worker_id)
                and compatible_recipe(body.recipe.model_dump(), w["capabilities"])
                for w in store.workers()
            ):
                raise ValueError(
                    "No worker has verified these settings. Connect a compatible worker or choose verified settings."
                )
            source = await asyncio.to_thread(inspect_source, path)
            if body.recipe.preview_frame_time is not None:
                from fractions import Fraction

                try:
                    rate = Fraction(source["frame_rate"])
                    if rate <= 0:
                        raise ValueError
                except (ValueError, ZeroDivisionError):
                    raise ValueError("This source has no declared frame rate. Use a full conventional resize or another video.") from None
                remaining = source["duration"] - body.recipe.preview_frame_time
                if remaining <= 0 or (body.recipe.frame_generation and remaining < 0.5):
                    raise ValueError("Choose an earlier frame. Motion previews need at least half a second remaining.")
                if body.recipe.hdr:
                    raise ValueError("Still comparison currently supports SDR. Use an HDR video preview on an HDR display.")
            if expected_source and source["sha256"] != expected_source["sha256"]:
                raise ValueError(
                    "The source changed after this preview. Create and review a new preview first."
                )
            if source["hdr"] or source["bit_depth"] != 8:
                raise ValueError(
                    "HDR and high-bit-depth sources are protected. This release accepts 8-bit SDR only; keep this source unchanged."
                )
            if body.recipe.frame_generation:
                from .frame_generation import FPS

                try:
                    from fractions import Fraction

                    incoming = Fraction(source["frame_rate"])
                    if incoming <= 0 or FPS[body.recipe.frame_rate] <= incoming:
                        raise ValueError("Choose a target above the source frame rate.")
                except (ZeroDivisionError, KeyError):
                    raise ValueError("Source frame rate is unavailable; refusing to guess motion timing.") from None
                if source["video_start_time"] is None or source["start_time"] is None:
                    raise ValueError("Source stream offsets are unavailable; refusing to guess synchronization.")
                if not any(
                    not w["revoked"] and (not body.worker_id or w["id"] == body.worker_id)
                    and compatible_recipe(body.recipe.model_dump(), w["capabilities"], source)
                    for w in store.workers()
                ):
                    raise ValueError("This target exceeds the verified native limit. Choose Auto or Cascade, or another worker.")
            if max(dimensions(source, body.recipe.model_dump())) > 7680:
                raise ValueError(
                    "Requested output exceeds this release's 8K safety limit. Choose a smaller scale."
                )
            if shutil.disk_usage(cfg.output).free < cfg.reserve_bytes:
                raise ValueError("Output drive has too little free space. Free space before queueing.")
            return public_job(store.add_job(body.path, body.recipe.model_dump(), source, body.worker_id))
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/jobs", dependencies=[Depends(admin)])
    async def add_job(body: JobCreate):
        return await queue_job(body)

    @app.post("/api/jobs/{identity}/full", dependencies=[Depends(admin)])
    async def full_from_preview(identity: str):
        job = store.job(identity)
        if not job or job["status"] != "completed" or not job["recipe"]["preview_seconds"]:
            raise HTTPException(409, "Complete a preview before continuing to the full video.")
        body = JobCreate(
            path=job["path"], recipe=job["recipe"] | {"preview_seconds": 0, "preview_frame_time": None}, worker_id=job["target"]
        )
        return await queue_job(body, expected_source=job["source"], require_compatible=True)

    @app.post("/api/jobs/{identity}/cancel", dependencies=[Depends(admin)])
    def cancel(identity: str):
        store.cancel(identity)
        return {"ok": True}

    @app.post("/api/jobs/{identity}/retry", dependencies=[Depends(admin)])
    def retry(identity: str):
        if not store.retry(identity):
            raise HTTPException(409, "Only failed or cancelled jobs can be retried.")
        return {"ok": True}

    @app.post("/api/worker/claim")
    def claim(item: Annotated[dict, Depends(worker)]):
        return {
            "job": store.claim(item, cfg.lease_seconds),
            "heartbeat_seconds": max(1, cfg.lease_seconds // 4),
        }

    @app.post("/api/worker/jobs/{identity}/heartbeat")
    def heartbeat(identity: str, body: Heartbeat, item: Annotated[dict, Depends(worker)]):
        if not store.heartbeat(
            identity, item["id"], body.lease, body.progress, body.stage, cfg.lease_seconds
        ):
            raise HTTPException(409, "Job cancelled or lease expired. Stop processing.")
        return {"ok": True}

    @app.get("/api/worker/jobs/{identity}/source")
    def source(identity: str, request: Request, item: Annotated[dict, Depends(worker)]):
        job = owned(identity, item, request.headers.get("x-job-lease", ""))
        try:
            path = beneath(cfg.library, job["path"], file=True)
            stat = path.stat()
            if stat.st_size != job["source"]["size"] or stat.st_mtime_ns != job["source"]["mtime_ns"]:
                raise ValueError("Source changed since this job was queued. Create a new job.")
            return FileResponse(path, filename=path.name)
        except (ValueError, OSError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/worker/jobs/{identity}/fail")
    def fail(identity: str, body: Failure, item: Annotated[dict, Depends(worker)]):
        owned(identity, item, body.lease)
        store.fail(identity, item["id"], body.lease, body.error)
        return {"ok": True}

    @app.put("/api/worker/jobs/{identity}/result")
    async def upload(identity: str, request: Request, item: Annotated[dict, Depends(worker)]):
        lease = request.headers.get("x-job-lease", "")
        job = owned(identity, item, lease)
        try:
            folder = beneath(cfg.output, job["recipe"]["output_directory"])
            folder.mkdir(parents=True, exist_ok=True)
            scratch = folder / f".{identity}-{secrets.token_hex(8)}.partial.mkv"
            stem = Path(job["path"]).stem[:140]
            kind = "preview" if job["recipe"]["preview_seconds"] else "sr"
            final = folder / f"{stem}.{kind}.{identity}.mkv"
            received = 0
            with scratch.open("xb") as out:
                async for chunk in request.stream():
                    received += len(chunk)
                    if received > cfg.max_upload_bytes:
                        raise ValueError("Output exceeds the configured upload limit.")
                    if shutil.disk_usage(folder).free < len(chunk) + cfg.reserve_bytes:
                        raise ValueError("Output drive is full. Original preserved.")
                    owned(identity, item, lease)
                    out.write(chunk)
                out.flush()
                os.fsync(out.fileno())
            if request.headers.get("x-output-sha256", "") != await asyncio.to_thread(sha256, scratch):
                raise ValueError("Transfer checksum did not match. Retry on a stable connection.")
            info = await media_call(validate_output, scratch, job["source"], job["recipe"])
            result = info | {"path": str(final.relative_to(cfg.output)), "bytes": received}
            # Serialize publication against cancel/revoke. The completed name is never overwritten.
            with store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT * FROM jobs WHERE id=? AND worker_id=? AND lease=? AND status='running' AND lease_until>?",
                    (identity, item["id"], lease, time.time()),
                ).fetchone()
                if not row:
                    raise ValueError("Job cancelled during upload. Result discarded.")
                os.link(scratch, final)
                try:
                    db.execute(
                        "UPDATE jobs SET status='completed',progress=100,stage='Ready',result=?,lease=NULL,updated=? WHERE id=?",
                        (json.dumps(result), time.time(), identity),
                    )
                except BaseException:
                    final.unlink(missing_ok=True)
                    raise
            return {"ok": True, "result": result}
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            if "scratch" in locals():
                scratch.unlink(missing_ok=True)

    @app.get("/api/jobs/{identity}/download", dependencies=[Depends(admin)])
    def download(identity: str):
        job = store.job(identity)
        if not job or job["status"] != "completed":
            raise HTTPException(404, "Finished video is not available.")
        try:
            path = beneath(cfg.output, job["result"]["path"], file=True)
            return FileResponse(path, filename=path.name)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/library/info", dependencies=[Depends(admin)])
    async def library_info(path: str):
        try:
            original = beneath(cfg.library, path, file=True)
            if original.suffix.lower() not in VIDEO_EXTENSIONS:
                raise ValueError("Choose a supported video file.")
            info = await media_call(probe, original)
            if info["hdr"] or info["bit_depth"] != 8:
                raise ValueError("Frame comparison currently supports 8-bit SDR video.")
            return {key: info[key] for key in ("duration", "width", "height", "frame_rate")}
        except (ValueError, OSError) as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/library/frame", dependencies=[Depends(admin)])
    async def library_frame(path: str, seconds: Annotated[float, Query(ge=0, allow_inf_nan=False)] = 0):
        try:
            original = beneath(cfg.library, path, file=True)
            if original.suffix.lower() not in VIDEO_EXTENSIONS:
                raise ValueError("Choose a supported video file.")
            info = await media_call(probe, original)
            if info["hdr"] or info["bit_depth"] != 8 or seconds >= info["duration"]:
                raise ValueError("Choose a frame within an 8-bit SDR video.")
            return Response(await media_call(frame_image, original, seconds), media_type="image/png")
        except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
            raise HTTPException(400, "Cannot preview this frame. Choose another time or video.") from exc

    @app.get("/api/jobs/{identity}/frame", dependencies=[Depends(admin)])
    async def comparison_frame(identity: str, side: Literal["original", "enhanced"]):
        job = store.job(identity)
        if not job or job["status"] != "completed" or not job["recipe"]["preview_seconds"]:
            raise HTTPException(409, "Complete a preview before comparing frames.")
        if job["recipe"].get("hdr"):
            raise HTTPException(409, "Review this HDR preview on an HDR display.")
        try:
            original = beneath(cfg.library, job["path"], file=True)
            stat = original.stat()
            if stat.st_size != job["source"]["size"] or stat.st_mtime_ns != job["source"]["mtime_ns"]:
                raise ValueError("Source changed. Create a new preview before comparing.")
            path = original if side == "original" else beneath(cfg.output, job["result"]["path"], file=True)
            seconds = (job["recipe"].get("preview_frame_time") or 0) if side == "original" else 0
            return Response(await media_call(frame_image, path, seconds), media_type="image/png")
        except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
            raise HTTPException(409, str(exc)) from exc

    static = Path(__file__).parent / "static"
    if static.is_dir():
        app.mount("/assets", StaticFiles(directory=static), name="assets")

    @app.get("/")
    def index():
        if not (static / "index.html").is_file():
            return Response("Build the Web UI with npm ci and npm run build before starting the manager.", status_code=503)
        return FileResponse(static / "index.html")

    return app
