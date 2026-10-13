"""Real frame extraction and paired preview-to-full delivery; no GPU substitutes."""

import asyncio
import io
import struct
import sys

import av
import httpx
import numpy as np

from popcorn_sr.frame_generation import adapter_process
from popcorn_sr.media import frame_image, sha256
from popcorn_sr.models import Recipe
from popcorn_sr.scratch import initialize
from popcorn_sr.worker import Worker
from tests.conftest import pair_worker


def png_pixels(data):
    with av.open(io.BytesIO(data)) as image:
        return next(image.decode(video=0)).to_ndarray(format="rgb24")


def run_claim(client, store, worker, claim):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app),
                                    base_url="http://testserver",
                                    headers={"Authorization": f"Bearer {worker.token}"}) as remote:
            await worker.run_job(remote, claim, 1)
    asyncio.run(run())
    result = store.job(claim["id"])
    assert result["status"] == "completed", result["error"]
    assert not list(worker.scratch.glob("job-*"))
    return result


def test_authenticated_seek_comparison_and_full_copy_preserve_original(setup, auth, tmp_path):
    client, store, cfg, source = setup
    original_hash = sha256(source)
    credentials, _ = pair_worker(client)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    initialize(scratch)
    worker = Worker("http://testserver", tmp_path / "worker-state", scratch)
    worker.token, worker.worker_id = credentials["token"], credentials["worker_id"]
    worker.reserve = 0
    recipe = Recipe(scale=2, preview_seconds=5, preview_frame_time=.35).model_dump()
    response = client.post("/api/jobs", json={"path": source.name, "recipe": recipe})
    assert response.status_code == 200, response.text
    queued = response.json()
    unavailable = client.get(f"/api/jobs/{queued['id']}/frame?side=enhanced")
    assert unavailable.status_code == 409
    claim = store.claim(store.worker(credentials["token"]), 90)
    result = run_claim(client, store, worker, claim)
    assert result["result"]["audio_streams"] == 0  # The still sample is explicitly video-only.
    assert result["result"]["duration"] < .8
    a = client.get(f"/api/jobs/{queued['id']}/frame?side=original")
    b = client.get(f"/api/jobs/{queued['id']}/frame?side=enhanced")
    assert a.status_code == b.status_code == 200
    assert a.headers["content-type"] == "image/png"
    assert a.headers["cache-control"] == b.headers["cache-control"] == "no-store"
    assert a.content == frame_image(source, .35)
    assert a.content != frame_image(source, 0)
    before, after = png_pixels(a.content), png_pixels(b.content)
    assert before.shape == (96, 128, 3) and after.shape == (192, 256, 3)
    # Downsample the actual encoded enhancement. A wrong selected picture is
    # visibly different in this moving test pattern, even at the same size.
    mismatch = np.mean(np.abs(before.astype(float) - after[::2, ::2].astype(float)))
    assert mismatch < 15, mismatch
    full = client.post(f"/api/jobs/{queued['id']}/full")
    assert full.status_code == 200, full.text
    assert full.json()["recipe"]["preview_frame_time"] is None
    assert full.json()["recipe"]["preview_seconds"] == 0
    completed = run_claim(client, store, worker, store.claim(store.worker(credentials["token"]), 90))
    assert completed["result"]["audio_streams"] == 1
    with av.open(str(cfg.output / completed["result"]["path"])) as video:
        assert len(list(video.decode(video=0))) == 24
    assert sha256(source) == original_hash
    # Reviewing a changed original cannot authorize the saved full run.
    source.write_bytes(source.read_bytes() + b"changed")
    assert client.get(f"/api/jobs/{queued['id']}/frame?side=original").status_code == 409
    assert client.post(f"/api/jobs/{queued['id']}/full").status_code == 400


def test_frame_paths_ranges_and_auth_fail_closed(setup, auth):
    client, _, cfg, source = setup
    info = client.get(f"/api/library/info?path={source.name}")
    assert info.status_code == 200 and info.json()["width"] == 128
    for path in ("../sample.mkv", str(source), "missing.mkv"):
        assert client.get("/api/library/frame", params={"path": path}).status_code == 400
    escape = cfg.library / "escape.mkv"
    escape.symlink_to(cfg.output / "outside.mkv")
    assert client.get("/api/library/frame", params={"path": escape.name}).status_code == 400
    for seconds in (-1, "nan", "inf"):
        assert client.get("/api/library/frame", params={"path": source.name, "seconds": seconds}).status_code == 422
    assert client.get("/api/library/frame", params={"path": source.name, "seconds": 100}).status_code == 400
    for recipe in (Recipe().model_dump() | {"preview_frame_time": .5},
                   Recipe(preview_seconds=5).model_dump() | {"preview_frame_time": -1}):
        assert client.post("/api/jobs", json={"path": source.name, "recipe": recipe}).status_code == 422
    response = client.post("/api/jobs", json={"path": source.name,
                           "recipe": Recipe(preview_seconds=5, preview_frame_time=100).model_dump()})
    assert response.status_code == 400
    client.headers.pop("Authorization")
    for url in (f"/api/library/info?path={source.name}", f"/api/library/frame?path={source.name}",
                "/api/jobs/missing/frame?side=original"):
        assert client.get(url).status_code == 401


def test_frame_display_is_bounded_without_writing_cache(tmp_path):
    import subprocess

    source = tmp_path / "4k.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:size=3840x2160:rate=1",
                    "-t", "1", "-threads", "2", "-c:v", "libx264", str(source)], check=True)
    frame = frame_image(source, 0)
    width, height = struct.unpack(">II", frame[16:24])
    assert (width, height) == (1920, 1080)
    assert list(tmp_path.iterdir()) == [source]


def test_multistage_progress_maps_each_native_pass_instead_of_resetting(tmp_path, capsys):
    command = [sys.executable, "-c", "print('out_time_us=0'); print('out_time_us=500000'); print('out_time_us=1000000')"]
    for index in range(3):
        adapter_process(command, progress_range=(index / 3, 1 / 3), duration=1)
    values = [float(line.split("=", 1)[1]) for line in capsys.readouterr().out.splitlines()]
    assert values == sorted(values)
    assert values[0] == 0 and values[-1] == 1
    assert .49 < values[4] < .51  # Second pass advances through the middle.

    worker = Worker("http://testserver", tmp_path / "worker", tmp_path)
    worker.status = {"progress": 55, "stage": "Generating DLSS frames"}
    asyncio.run(worker.process([sys.executable, "-c", "print('pipeline_progress=0.5')"], tmp_path, 1,
                              progress_start=55, progress_end=83))
    assert worker.status["progress"] == 69
