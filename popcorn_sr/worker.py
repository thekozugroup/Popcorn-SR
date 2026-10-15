import asyncio
import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .engines import (
    detect_capabilities,
    engine_result,
    frame_generation_command,
    hdr_command,
    processing_command,
)
from .media import output_suffix, preserved_command, probe, validate_output
from .scratch import atomic_private_json, read_marker
from .storage_plan import estimate_scratch_bytes
from .updates import WorkerUpdates


@contextmanager
def exclusive_file(path):
    """Linux locks also survive in the processing child if the parent crashes."""
    import fcntl

    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield fd
    finally:
        os.close(fd)


class Worker:
    def __init__(self, manager: str, state: Path, scratch: Path, name: str | None = None):
        parsed = urlparse(manager)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Manager must be an HTTP(S) address without credentials or query parameters.")
        self.manager = manager.rstrip("/")
        self.state = state
        self.scratch = scratch.resolve()
        self.name = name or socket.gethostname()
        self.token = ""
        self.reserve = int(os.environ.get("POPCORN_SCRATCH_RESERVE_MIB", "1024")) * 1024**2
        self.capabilities = {}
        self.updates = WorkerUpdates()
        state.mkdir(parents=True, exist_ok=True)
        self.credential_file = state / "worker.json"
        self.status = {"progress": 0, "stage": "Receiving source"}
        self.drive_id = None
        self.worker_id = None
        self.active_fd = None
        self.scratch_identity_file = state / "scratch.json"
        self.expected_scratch = (
            json.loads(self.scratch_identity_file.read_text())
            if self.scratch_identity_file.exists()
            else None
        )

    def storage(self):
        marker = read_marker(self.scratch)
        identity = marker["drive_id"]
        if self.drive_id is not None and identity != self.drive_id:
            raise ValueError("Scratch drive identity changed. Stop and verify the intended mounted drive.")
        self.drive_id = identity
        observed = {key: marker[key] for key in ("drive_id", "filesystem_id")}
        if self.expected_scratch is not None and observed != self.expected_scratch:
            raise ValueError(
                "Scratch drive changed since pairing. Mount the original drive or use a new worker state folder."
            )
        if self.expected_scratch is None:
            atomic_private_json(self.scratch_identity_file, observed)
            self.expected_scratch = observed
        usage = shutil.disk_usage(self.scratch)
        return {
            "path": str(self.scratch),
            "free_bytes": usage.free,
            "total_bytes": usage.total,
            **observed,
            "reserve_bytes": self.reserve,
        }

    async def connect(self, pair_code=None):
        storage = self.storage()
        if storage["free_bytes"] < self.reserve:
            raise ValueError("Temporary drive has less than the reserved space. Free space before starting the worker.")
        checking = {
            "initialization": "checking", "engines": [], "encoders": [], "device": "",
            "platform": platform.system(), "architecture": platform.machine(), "notes": {},
            "dlss_sr": {}, "dlss_frame_generation": {}, "rtx_hdr": {}, "rtx_vsr": {},
        }
        self.capabilities = checking
        # Consume the short-lived code and save credentials before GPU checks.
        await self.authenticate(pair_code)
        async with self.client() as client:
            try:
                # Saved credentials must also be validated before using the GPU.
                await self.publish_status(client)
                detected = await self.check_support(client)
                if not detected["encoders"]:
                    raise ValueError("No encoder passed its processing test. Install FFmpeg with supported codecs.")
                self.capabilities = detected | {"initialization": "ready"}
                await self.publish_status(client)
            except BaseException as exc:
                if isinstance(exc, asyncio.CancelledError):
                    message = "Support checks stopped. Restart the worker to continue."
                elif isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 401:
                    message = "Worker pairing was revoked. Pair again using a new state folder."
                elif isinstance(exc, httpx.HTTPError):
                    message = "Manager connection interrupted during support checks. Restart the worker when connected."
                else:
                    message = str(exc)
                self.capabilities = checking | {"initialization": "failed", "initialization_error": message}
                try:
                    storage = self.storage()
                except (ValueError, OSError):
                    storage = {"path": str(self.scratch), "available": False}
                try:
                    await self.publish_status(client, storage, timeout=2)
                except httpx.HTTPError:
                    pass
                if isinstance(exc, httpx.HTTPError):
                    raise ValueError(message) from None
                raise

    async def authenticate(self, pair_code=None):
        if self.credential_file.exists():
            saved = json.loads(self.credential_file.read_text())
            if saved["manager"] != self.manager:
                raise ValueError(
                    "Saved pairing belongs to another manager. Use a separate worker state folder."
                )
            self.token = saved["token"]
            self.worker_id = saved["worker_id"]
            return
        if not pair_code:
            raise ValueError(
                "This worker is not paired. Create a pairing code in the manager and set POPCORN_PAIR_CODE."
            )
        async with self.client() as client:
            response = await client.post(
                "/api/workers/pair",
                json={
                    "code": pair_code,
                    "name": self.name,
                    "capabilities": self.capabilities,
                    "scratch": self.storage(),
                },
                timeout=30,
            )
            if response.status_code in {400, 422}:
                raise ValueError("Pairing code is invalid, expired or already used. Create a new code.")
            response.raise_for_status()
            data = response.json()
        self.token = data["token"]
        self.worker_id = data["worker_id"]
        atomic_private_json(self.credential_file, data | {"manager": self.manager})

    async def publish_status(self, client, storage=None, *, timeout=10):
        self.capabilities["updates"] = self.updates.status()
        self.updates.runtime(self.capabilities)
        response = await client.post(
            "/api/worker/status",
            json={"capabilities": self.capabilities, "scratch": self.storage() if storage is None else storage},
            timeout=timeout,
        )
        response.raise_for_status()
        if identity := response.json().get("update_request"):
            self.updates.request(identity)

    async def initialization_heartbeat(self, client, finished, interval=10):
        failed_since = None
        while not finished.is_set():
            try:
                await asyncio.wait_for(finished.wait(), timeout=interval)
                return
            except TimeoutError:
                pass
            try:
                await self.publish_status(client)
                failed_since = None
            except (httpx.TimeoutException, httpx.NetworkError):
                failed_since = failed_since or time.monotonic()
                if time.monotonic() - failed_since > 30:
                    raise ValueError("Manager connection interrupted during support checks. Restart when connected.") from None

    async def check_support(self, client):
        check = Path(tempfile.mkdtemp(prefix="capability-check-", dir=self.scratch))
        stopped, finished = threading.Event(), asyncio.Event()
        detection = asyncio.create_task(asyncio.to_thread(detect_capabilities, check, stopped))
        keepalive = asyncio.create_task(self.initialization_heartbeat(client, finished))
        monitor = asyncio.create_task(self.monitor_storage())
        try:
            done, _ = await asyncio.wait((detection, keepalive, monitor), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
            return detection.result()
        finally:
            # Stop native child groups before reporting failure. Let any in-flight
            # checking heartbeat finish before publishing the final ready state.
            stopped.set()
            finished.set()
            monitor.cancel()
            await asyncio.gather(detection, keepalive, monitor, return_exceptions=True)
            try:
                self.storage()
            except (ValueError, OSError):
                pass  # Never remove files through a replaced or unavailable drive.
            else:
                shutil.rmtree(check, ignore_errors=True)

    def client(self):
        return httpx.AsyncClient(
            base_url=self.manager,
            headers={"Authorization": f"Bearer {self.token}"} if self.token else {},
            timeout=httpx.Timeout(60, read=60, write=60),
            follow_redirects=False,
        )

    async def heartbeat(self, client, job, interval):
        failed_since = None
        while True:
            await asyncio.sleep(interval)
            storage = self.storage()
            if storage["free_bytes"] < self.reserve:
                raise ValueError("Scratch drive is full. Processing stopped to preserve the drive reserve.")
            try:
                response = await client.post(
                    f"/api/worker/jobs/{job['id']}/heartbeat", json={"lease": job["lease"], **self.status}
                )
                response.raise_for_status()
                failed_since = None
            except (httpx.TimeoutException, httpx.NetworkError):
                failed_since = failed_since or time.monotonic()
                if time.monotonic() - failed_since > interval * 2:
                    raise ValueError(
                        "Manager connection interrupted. Processing stopped; retry when connected."
                    ) from None

    async def monitor_storage(self, interval=1):
        """Drive failure must not wait for a slow or disconnected heartbeat."""
        while True:
            await asyncio.sleep(interval)
            if self.storage()["free_bytes"] < self.reserve:
                raise ValueError("Scratch drive is full. Processing stopped to preserve the drive reserve.")

    async def process(self, command, folder, duration, *, progress_start=10, progress_end=85):
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("POPCORN_ADMIN") or key == "POPCORN_PAIR_CODE":
                env.pop(key, None)
        env.update(
            {
                "TMPDIR": str(folder),
                "TEMP": str(folder),
                "TMP": str(folder),
                "XDG_CACHE_HOME": str(self.scratch / "cache"),
                "CUDA_CACHE_PATH": str(self.scratch / "cache" / "cuda"),
            }
        )
        extra = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        if os.name == "posix" and self.active_fd is not None:
            extra["pass_fds"] = (self.active_fd,)
            env["POPCORN_ACTIVE_JOB_FD"] = str(self.active_fd)
        else:
            env.pop("POPCORN_ACTIVE_JOB_FD", None)
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=folder,
            **extra,
        )
        tail = bytearray()

        async def errors():
            while chunk := await process.stderr.read(8192):
                tail.extend(chunk)
                if len(tail) > 8192:
                    del tail[:-8192]

        async def progress():
            while line := await process.stdout.readline():
                if line.startswith((b"out_time_us=", b"pipeline_progress=")):
                    try:
                        value = float(line.split(b"=", 1)[1])
                        fraction = value if line.startswith(b"pipeline_progress=") else value / 1_000_000 / duration
                        self.status["progress"] = max(self.status["progress"], progress_start + min(1, max(0, fraction)) * (progress_end - progress_start))
                    except ValueError:
                        pass

        readers = [asyncio.create_task(errors()), asyncio.create_task(progress())]
        try:
            code = await process.wait()
            await asyncio.gather(*readers)
            if code:
                raise ValueError("Processing engine failed: " + tail.decode(errors="replace")[-1500:])
        finally:
            if os.name == "posix":
                # The engine may have exited while a descendant still holds its
                # pipes or scratch lock. Terminate the entire owned group.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
            elif process.returncode is None:
                if os.name == "nt":
                    killer = await asyncio.create_subprocess_exec(
                        "taskkill",
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                    await killer.wait()
                await process.wait()
            for task in readers:
                task.cancel()
            await asyncio.gather(*readers, return_exceptions=True)

    async def perform(self, client, job, folder):
        source = folder / ("source" + Path(job["path"]).suffix.lower())
        digest = hashlib.sha256()
        received = 0
        async with client.stream(
            "GET", f"/api/worker/jobs/{job['id']}/source", headers={"X-Job-Lease": job["lease"]}
        ) as response:
            response.raise_for_status()
            with source.open("xb") as stream:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    self.storage()
                    if shutil.disk_usage(self.scratch).free < len(chunk) + self.reserve:
                        raise ValueError("Scratch drive is full during transfer.")
                    received += len(chunk)
                    if received > job["source"]["size"]:
                        raise ValueError("Source transfer exceeded the expected size.")
                    stream.write(chunk)
                    digest.update(chunk)
                    self.status["progress"] = min(10, received / max(1, job["source"]["size"]) * 10)
        if received != job["source"]["size"] or digest.hexdigest() != job["source"]["sha256"]:
            raise ValueError("Source checksum changed or transfer was incomplete. Original preserved.")
        info = await asyncio.to_thread(probe, source)
        recipe = job["recipe"]
        suffix = output_suffix(job["source"], recipe)
        output = folder / ("result" + suffix)
        frame_preview = recipe.get("preview_frame_time") is not None
        engine_source = source
        if frame_preview or (recipe["engine"] != "resize" and recipe["preview_seconds"]):
            # Clip before invoking external engines; the heavy engine never reads the full preview source.
            engine_source = folder / "preview-source.mkv"
            interpreter = os.environ.get("POPCORN_AI_PYTHON" if recipe["engine"] in {"rtx-vsr", "realesrgan", "flashvsr"} else "POPCORN_NGX_PYTHON", sys.executable)
            await self.process(
                [interpreter, "-m", "popcorn_sr.preview_sample", "--input", str(source),
                 "--output", str(engine_source), "--start", str(recipe.get("preview_frame_time") or 0),
                 "--seconds", str(recipe["preview_seconds"]), "--clock", "video" if frame_preview else "container"],
                folder, recipe["preview_seconds"], progress_start=10, progress_end=15,
            )
        self.status["stage"] = "Enhancing video" if recipe["engine"] != "resize" else "Encoding video"
        from .media import preview_duration

        duration = preview_duration(info, recipe)
        generation = recipe.get("frame_generation", False)
        hdr = recipe.get("hdr", False)
        source_end = None
        if generation or hdr:
            # A process-group child can stop immediately on cancel, storage
            # loss or manager disconnection; a decoding thread cannot.
            stage = self.status["stage"]
            self.status["stage"] = "Checking video timing"
            timing_report = folder / "source-timing.json"
            interpreter = os.environ.get("POPCORN_AI_PYTHON" if hdr or recipe["engine"] == "rtx-vsr" else "POPCORN_NGX_PYTHON", sys.executable)
            await self.process([interpreter, "-m", "popcorn_sr.timeline", "--input", str(engine_source),
                                "--report", str(timing_report)], folder, duration, progress_start=15, progress_end=18)
            source_end = Fraction(json.loads(timing_report.read_text())["duration"])
            self.status["stage"] = stage
            if recipe["preview_seconds"]:
                source_end = min(source_end, recipe["preview_seconds"])
        initial_output = folder / "upscaled.nut" if generation or hdr else output
        initial_recipe = recipe | {"codec": "ffv1"} if generation or hdr else recipe
        await self.process(processing_command(engine_source, initial_output, initial_recipe, info), folder, duration,
                           progress_start=18 if generation or hdr else 15,
                           progress_end=55 if generation or hdr else 83)
        rendered = engine_result(recipe["engine"], initial_output) if recipe["engine"] != "resize" else initial_output
        timing = None
        if generation:
            self.status["stage"] = "Generating DLSS frames"
            report = folder / "frame-generation.json"
            generated = folder / "generated.nut" if hdr else output
            generation_recipe = recipe | {"codec": "ffv1"} if hdr else recipe
            await self.process(frame_generation_command(rendered, generated, generation_recipe, report,
                                                       end_time=source_end), folder, duration,
                               progress_start=55, progress_end=80 if hdr else 83)
            timing = json.loads(report.read_text())
            rendered.unlink()
            rendered = generated
        if hdr:
            self.status["stage"] = "Converting to HDR"
            end = timing["source_video_duration"] if timing else source_end
            await self.process(hdr_command(rendered, output, recipe, end_time=end), folder, duration,
                               progress_start=80 if generation else 55, progress_end=83)
            rendered.unlink()
            rendered = output
        if not frame_preview and (recipe["engine"] != "resize" or generation or hdr):
            # Remux original streams ourselves: third-party exporters may discard subtitles or re-encode audio.
            remuxed = folder / ("preserved" + suffix)
            command = await asyncio.to_thread(preserved_command, rendered, source, remuxed, recipe, info, timing)
            await self.process(command, folder, duration, progress_start=83, progress_end=85)
            rendered = remuxed
        self.status.update(progress=86, stage="Checking result")
        result = await asyncio.to_thread(validate_output, rendered, job["source"], recipe)
        self.status.update(progress=90, stage="Returning video")
        size = rendered.stat().st_size

        async def content():
            sent = 0
            with rendered.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    sent += len(chunk)
                    self.status["progress"] = min(99, 90 + sent / max(1, size) * 9)
                    yield chunk

        response = await client.put(
            f"/api/worker/jobs/{job['id']}/result",
            content=content(),
            headers={
                "X-Job-Lease": job["lease"],
                "X-Output-SHA256": result["sha256"],
                "Content-Length": str(size),
                "Content-Type": "application/octet-stream",
            },
        )
        response.raise_for_status()

    async def run_job(self, client, job, interval):
        folder = self.scratch / f"job-{job['id']}-{job['lease'][:8]}"
        self.status = {"progress": 0, "stage": "Receiving source"}
        tasks = []
        job_lock = None
        created = False

        async def stop_processing():
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            tasks.clear()

        async def report_failure(message):
            # A disconnected manager must not delay GPU shutdown or scratch cleanup.
            try:
                async with asyncio.timeout(2):
                    await client.post(
                        f"/api/worker/jobs/{job['id']}/fail",
                        json={"lease": job["lease"], "error": message[:2000]},
                    )
            except (httpx.HTTPError, TimeoutError):
                pass

        try:
            storage = self.storage()
            required = estimate_scratch_bytes(job["source"], job["recipe"], self.capabilities) + self.reserve
            if storage["free_bytes"] < required:
                if job["recipe"].get("frame_generation"):
                    action = (
                        "Free space or use a larger temporary drive."
                        if job["recipe"].get("preview_seconds") == 5
                        else "Use a larger temporary drive or a shorter preview."
                    )
                    raise ValueError(
                        f"Frame generation needs about {required / 1024**3:.2f} GiB of free temporary storage; "
                        f"{storage['free_bytes'] / 1024**3:.2f} GiB is available. {action}"
                    )
                raise ValueError("Scratch drive has too little space. Free at least 4× the source size plus the reserve.")
            folder.mkdir(exist_ok=False)
            created = True
            atomic_private_json(
                folder / ".popcorn-job.json",
                {
                    "version": 1,
                    "worker_id": job["worker_id"],
                    "job_id": job["id"],
                    "lease": job["lease"],
                    "drive_id": self.drive_id,
                },
            )
            if os.name == "posix":
                job_lock = exclusive_file(folder / ".popcorn-active.lock")
                self.active_fd = job_lock.__enter__()
            tasks = [
                asyncio.create_task(self.perform(client, job, folder)),
                asyncio.create_task(self.heartbeat(client, job, interval)),
                asyncio.create_task(self.monitor_storage()),
            ]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except asyncio.CancelledError:
            await stop_processing()
            await report_failure("Worker stopped. Review and retry when it is online.")
            raise
        except (ValueError, OSError, httpx.HTTPError) as exc:
            await stop_processing()
            message = str(exc)
            if isinstance(exc, httpx.HTTPError):
                message = "Manager rejected the request or the connection was interrupted. Check pairing and network, then retry."
            await report_failure(message)
            print(f"Job {job['id']} stopped. {message[:200]}", flush=True)
        finally:
            await stop_processing()
            self.active_fd = None
            if job_lock is not None:
                job_lock.__exit__(None, None, None)
            if created:
                try:
                    self.storage()
                    shutil.rmtree(folder, ignore_errors=True)
                except (ValueError, OSError):
                    print(
                        "Scratch drive unavailable; owned job files will be recovered after it returns.",
                        flush=True,
                    )

    async def recover_scratch(self, client):
        """Remove only this worker's inactive scratch jobs, never unknown folders."""
        self.storage()
        if os.name != "posix":
            return
        for folder in self.scratch.glob("job-*"):
            marker = folder / ".popcorn-job.json"
            if (
                folder.is_symlink()
                or marker.is_symlink()
                or not marker.is_file()
                or marker.stat().st_size > 4096
            ):
                continue
            try:
                data = json.loads(marker.read_text())
                if (
                    not isinstance(data, dict)
                    or data.get("version") != 1
                    or data.get("worker_id") != self.worker_id
                    or data.get("drive_id") != self.drive_id
                    or not isinstance(data.get("lease"), str)
                    or folder.name != f"job-{data.get('job_id')}-{data['lease'][:8]}"
                ):
                    continue
                with exclusive_file(folder / ".popcorn-active.lock"):
                    response = await client.post(
                        f"/api/worker/jobs/{data['job_id']}/fail",
                        json={
                            "lease": data["lease"],
                            "error": "Worker restarted. Review and retry this job.",
                        },
                    )
                    if response.status_code not in {200, 409}:
                        response.raise_for_status()
                    self.storage()
                    shutil.rmtree(folder)
            except (OSError, json.JSONDecodeError):
                continue

    async def _run(self, pair_code=None):
        await self.connect(pair_code)
        print(f"Worker ready: {self.name}. Engines: {', '.join(self.capabilities['engines'])}.", flush=True)
        async with self.client() as client:
            recover_at = 0
            while True:
                try:
                    await self.publish_status(client)
                    if self.updates.draining():
                        self.updates.runtime(self.capabilities, idle=True)
                        await asyncio.sleep(3)
                        continue
                    if time.monotonic() >= recover_at:
                        await self.recover_scratch(client)
                        recover_at = time.monotonic() + 60
                    response = await client.post("/api/worker/claim")
                    response.raise_for_status()
                    data = response.json()
                    if data["job"]:
                        await self.run_job(client, data["job"], data["heartbeat_seconds"])
                    else:
                        await asyncio.sleep(3)
                except httpx.HTTPError as exc:
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 401:
                        raise ValueError(
                            "Worker pairing was revoked. Pair again using a new state folder."
                        ) from None
                    print("Manager unreachable. Reconnecting in 5 seconds.", flush=True)
                    await asyncio.sleep(5)

    async def run(self, pair_code=None):
        if os.name == "posix":
            try:
                with exclusive_file(self.state / "worker.lock"):
                    await self._run(pair_code)
            except BlockingIOError:
                raise ValueError(
                    "Another worker is using this state folder. Stop it or choose a separate folder."
                ) from None
        else:
            await self._run(pair_code)
