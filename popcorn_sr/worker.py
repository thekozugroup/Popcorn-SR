import asyncio
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .engines import detect_capabilities, engine_result, frame_generation_command, processing_command
from .media import preserved_command, probe, validate_output
from .scratch import atomic_private_json, read_marker


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
        self.storage()
        import tempfile

        check = Path(tempfile.mkdtemp(prefix="capability-check-", dir=self.scratch))
        stopped = threading.Event()
        detection = asyncio.create_task(asyncio.to_thread(detect_capabilities, check, stopped))
        try:
            self.capabilities = await asyncio.shield(detection)
        except asyncio.CancelledError:
            stopped.set()
            try:
                await detection
            except ValueError:
                pass
            raise
        finally:
            shutil.rmtree(check, ignore_errors=True)
        if not self.capabilities["encoders"]:
            raise ValueError("No encoder passed its processing test. Install FFmpeg with supported codecs.")
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
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.manager}/api/workers/pair",
                json={
                    "code": pair_code,
                    "name": self.name,
                    "capabilities": self.capabilities,
                    "scratch": self.storage(),
                },
            )
            response.raise_for_status()
            data = response.json()
        self.token = data["token"]
        self.worker_id = data["worker_id"]
        atomic_private_json(self.credential_file, data | {"manager": self.manager})

    def client(self):
        return httpx.AsyncClient(
            base_url=self.manager,
            headers={"Authorization": f"Bearer {self.token}"},
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

    async def process(self, command, folder, duration):
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
                if line.startswith(b"out_time_us="):
                    try:
                        seconds = int(line.split(b"=", 1)[1]) / 1_000_000
                        self.status["progress"] = min(85, 10 + seconds / duration * 75)
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
        output = folder / "result.mkv"
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
        engine_source = source
        if recipe["engine"] != "resize" and recipe["preview_seconds"]:
            # Clip before invoking external engines; the heavy engine never reads the full preview source.
            engine_source = folder / "preview-source.mkv"
            await self.process(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(source),
                    "-t",
                    str(recipe["preview_seconds"]),
                    "-map",
                    "0:V:0",
                    "-an",
                    "-sn",
                    "-c:v",
                    "ffv1",
                    "-n",
                    str(engine_source),
                ],
                folder,
                recipe["preview_seconds"],
            )
        self.status["stage"] = "Enhancing video" if recipe["engine"] != "resize" else "Encoding video"
        duration = (
            min(info["duration"], recipe["preview_seconds"])
            if recipe["preview_seconds"]
            else info["duration"]
        )
        generation = recipe.get("frame_generation", False)
        initial_output = folder / "upscaled.nut" if generation else output
        initial_recipe = recipe | {"codec": "ffv1"} if generation else recipe
        await self.process(processing_command(engine_source, initial_output, initial_recipe, info), folder, duration)
        rendered = engine_result(recipe["engine"], initial_output) if recipe["engine"] != "resize" else initial_output
        timing = None
        if generation:
            self.status["stage"] = "Generating DLSS frames"
            report = folder / "frame-generation.json"
            await self.process(frame_generation_command(rendered, output, recipe, report), folder, duration)
            timing = json.loads(report.read_text())
            rendered.unlink()
            rendered = output
        if recipe["engine"] != "resize" or generation:
            # Remux original streams ourselves: third-party exporters may discard subtitles or re-encode audio.
            remuxed = folder / "preserved.mkv"
            await self.process(preserved_command(rendered, source, remuxed, recipe, info, timing), folder, duration)
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
            # Conservative estimate, with continuous checks while transferring.
            if storage["free_bytes"] < job["source"]["size"] * 4 + self.reserve:
                raise ValueError(
                    "Scratch drive has too little space. Free at least 4× the source size plus the reserve."
                )
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
                    response = await client.post(
                        "/api/worker/status",
                        json={"capabilities": self.capabilities, "scratch": self.storage()},
                    )
                    response.raise_for_status()
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
