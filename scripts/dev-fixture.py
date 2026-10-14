#!/usr/bin/env python3
"""Local test-only workspace. Uses generated video and a real CPU worker."""

import json
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import uvicorn

from popcorn_sr.config import Settings
from popcorn_sr.server import create_app
from popcorn_sr.worker import Worker

with tempfile.TemporaryDirectory(prefix="popcorn-browser-") as temp:
    root = Path(temp)
    library, scratch, worker_state = root / "library", root / "scratch", root / "worker"
    library.mkdir()
    scratch.mkdir()
    worker_state.mkdir()
    (scratch / ".popcorn-scratch").write_text("local-browser-check")
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "6",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(library / "A clearer picture.mkv"),
        ],
        check=True,
    )
    # A second generated input makes the actual batch path reviewable.
    shutil.copyfile(library / "A clearer picture.mkv", library / "Another moment.mkv")
    app = create_app(
        Settings(
            root / "state", library, root / "output", "local-test-only-access-key-12345", reserve_bytes=0, public_url="http://localhost:18877"
        )
    )
    app.state.auth.provision("admin", "local-test-only-password-12345")
    credentials = app.state.store.pair(
        app.state.store.pair_code(),
        "Local CPU worker",
        {
            "engines": ["resize"],
            "encoders": ["h264_cpu"],
            "device": "Local CPU",
            "platform": "Linux / macOS verification",
            "architecture": "local",
        },
        {"path": str(scratch), "free_bytes": 50 * 1024**3},
    )
    (worker_state / "worker.json").write_text(json.dumps(credentials | {"manager": "http://127.0.0.1:18877"}))

    def run_worker():
        import asyncio
        import time

        time.sleep(1)
        worker = Worker("http://127.0.0.1:18877", worker_state, scratch, "Local CPU worker")
        worker.reserve = 0
        asyncio.run(worker.run())

    threading.Thread(target=run_worker, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=18877, access_log=False)
