import asyncio
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .engines import detect_capabilities, engine_result, processing_command
from .media import probe, validate_output


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

    def storage(self):
        marker = self.scratch / ".popcorn-scratch"
        if not marker.is_file() or not marker.read_text().strip():
            raise ValueError("Scratch drive is not ready. Mount the drive and run init-scratch on that path.")
        usage = shutil.disk_usage(self.scratch)
        return {
            "path": str(self.scratch),
            "free_bytes": usage.free,
            "total_bytes": usage.total,
            "drive_id": marker.read_text().strip(),
            "reserve_bytes": self.reserve,
        }

    async def connect(self, pair_code=None):
        self.storage()
        check = self.scratch / "capability-check"
        check.mkdir(exist_ok=True)
        try:
            self.capabilities = await asyncio.to_thread(detect_capabilities, check)
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
        temporary = self.state / "worker.json.tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(data | {"manager": self.manager}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.credential_file)

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
            self.storage()
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
            }
        )
        extra = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {"start_new_session": True}
        )
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
            if process.returncode is None:
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
                else:
                    os.killpg(process.pid, signal.SIGKILL)
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
        await self.process(processing_command(engine_source, output, recipe, info), folder, duration)
        rendered = engine_result(recipe["engine"], output) if recipe["engine"] != "resize" else output
        if recipe["engine"] != "resize":
            # Remux original streams ourselves: third-party exporters may discard subtitles or re-encode audio.
            remuxed = folder / "preserved.mkv"
            cmd = [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(rendered),
                "-i",
                str(source),
                "-map",
                "0:V:0",
                "-map",
                "1:a?",
                "-map",
                "1:s?",
                "-map",
                "1:t?",
                "-map_metadata",
                "1",
                "-map_chapters",
                "1",
                "-c",
                "copy",
            ]
            if recipe["preview_seconds"]:
                cmd += ["-t", str(recipe["preview_seconds"])]
            await self.process([*cmd, "-n", str(remuxed)], folder, duration)
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
        try:
            storage = self.storage()
            # Conservative estimate, with continuous checks while transferring.
            if storage["free_bytes"] < job["source"]["size"] * 4 + self.reserve:
                raise ValueError(
                    "Scratch drive has too little space. Free at least 4× the source size plus the reserve."
                )
            folder.mkdir(exist_ok=False)
            tasks = [
                asyncio.create_task(self.perform(client, job, folder)),
                asyncio.create_task(self.heartbeat(client, job, interval)),
            ]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except asyncio.CancelledError:
            raise
        except (ValueError, OSError, httpx.HTTPError) as exc:
            message = str(exc)
            if isinstance(exc, httpx.HTTPError):
                message = "Manager rejected the request or the connection was interrupted. Check pairing and network, then retry."
            try:
                await client.post(
                    f"/api/worker/jobs/{job['id']}/fail",
                    json={"lease": job["lease"], "error": message[:2000]},
                )
            except httpx.HTTPError:
                pass
            print(f"Job {job['id']} stopped. {message[:200]}", flush=True)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            shutil.rmtree(folder, ignore_errors=True)

    async def run(self, pair_code=None):
        await self.connect(pair_code)
        print(f"Worker ready: {self.name}. Engines: {', '.join(self.capabilities['engines'])}.", flush=True)
        async with self.client() as client:
            while True:
                try:
                    response = await client.post(
                        "/api/worker/status",
                        json={"capabilities": self.capabilities, "scratch": self.storage()},
                    )
                    response.raise_for_status()
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
