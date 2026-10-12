import asyncio
import hashlib
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from popcorn_sr.media import ffmpeg_command, inspect_source, sha256
from popcorn_sr.models import Recipe
from popcorn_sr.worker import Worker
from tests.conftest import pair_worker


def test_auth_pairing_is_single_use_and_revocable(setup, auth):
    client, store, cfg, _ = setup
    client.headers.pop("Authorization")
    assert client.get("/api/state").status_code == 401
    assert client.post("/api/login", json={"token": "wrong"}).status_code == 401
    assert client.post("/api/login", json={"token": cfg.admin_token}).status_code == 200
    assert "HttpOnly" in client.cookies.__repr__() or client.get("/api/state").status_code == 200
    credentials, payload = pair_worker(client)
    assert client.post("/api/workers/pair", json=payload).status_code == 400
    assert credentials["token"] not in str(client.get("/api/state").json())
    client.post(f"/api/workers/{credentials['worker_id']}/revoke")
    client.cookies.clear()
    assert (
        client.post(
            "/api/worker/claim", headers={"Authorization": f"Bearer {credentials['token']}"}
        ).status_code
        == 401
    )
    assert store.worker(credentials["token"]) is None


def test_paths_and_hdr_fail_closed(setup, auth):
    client, _, cfg, clip = setup
    recipe = Recipe().model_dump()
    for path in ["../sample.mkv", str(clip), "missing.mkv"]:
        assert client.post("/api/jobs", json={"path": path, "recipe": recipe}).status_code == 400
    recipe["output_directory"] = "../library"
    assert client.post("/api/jobs", json={"path": "sample.mkv", "recipe": recipe}).status_code == 400
    escape = cfg.library / "escape.mkv"
    escape.symlink_to(cfg.output / "outside.mkv")
    assert (
        client.post("/api/jobs", json={"path": "escape.mkv", "recipe": Recipe().model_dump()}).status_code
        == 400
    )
    hdr = cfg.library / "hdr.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(clip),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p10le",
            "-x264-params",
            "colorprim=bt2020:transfer=smpte2084:colormatrix=bt2020nc",
            "-c:a",
            "copy",
            str(hdr),
        ],
        check=True,
    )
    response = client.post("/api/jobs", json={"path": hdr.name, "recipe": Recipe().model_dump()})
    assert response.status_code == 400 and "HDR" in response.json()["detail"]


def test_real_media_roundtrip_and_checksum_rejection(setup, auth, tmp_path):
    client, store, cfg, clip = setup
    original = sha256(clip)
    credentials, _ = pair_worker(client)
    recipe = Recipe(scale=2).model_dump()
    queued = client.post("/api/jobs", json={"path": clip.name, "recipe": recipe}).json()
    headers = {"Authorization": f"Bearer {credentials['token']}"}
    claim = client.post("/api/worker/claim", headers=headers).json()["job"]
    headers["X-Job-Lease"] = claim["lease"]
    download = client.get(f"/api/worker/jobs/{claim['id']}/source", headers=headers)
    assert hashlib.sha256(download.content).hexdigest() == original
    encoded = tmp_path / "result.mkv"
    subprocess.run(
        ffmpeg_command(clip, encoded, recipe, inspect_source(clip)), check=True, capture_output=True
    )
    data = encoded.read_bytes()
    headers["X-Output-SHA256"] = "wrong"
    rejected = client.put(f"/api/worker/jobs/{claim['id']}/result", content=data, headers=headers)
    assert rejected.status_code == 400
    assert not list(cfg.output.rglob("*.mkv"))
    headers["X-Output-SHA256"] = sha256(encoded)
    response = client.put(f"/api/worker/jobs/{claim['id']}/result", content=data, headers=headers)
    assert response.status_code == 200, response.text
    completed = store.job(queued["id"])
    assert completed["status"] == "completed"
    assert completed["result"]["audio_streams"] == 1
    assert completed["result"]["width"] == 256
    assert sha256(clip) == original
    assert client.get(f"/api/jobs/{claim['id']}/download").content == data
    assert (
        client.put(f"/api/worker/jobs/{claim['id']}/result", content=data, headers=headers).status_code == 409
    )


def test_lease_exclusivity_cancel_expiry_and_retry(setup, auth):
    client, store, cfg, clip = setup
    credentials, _ = pair_worker(client)
    worker = store.worker(credentials["token"])
    queued = store.add_job(clip.name, Recipe().model_dump(), inspect_source(clip))
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: store.claim(worker, 4), range(4)))
    assert sum(c is not None for c in claims) == 1
    claim = next(c for c in claims if c)
    store.cancel(claim["id"])
    assert not store.heartbeat(claim["id"], worker["id"], claim["lease"], 50, "Encoding", 4)
    assert store.retry(claim["id"])
    claim = store.claim(worker, 4)
    with store.connect() as db:
        db.execute("UPDATE jobs SET lease_until=? WHERE id=?", (time.time() - 1, claim["id"]))
    assert store.claim(worker, 4) is None
    assert store.job(queued["id"])["status"] == "failed"
    assert store.retry(queued["id"])


def test_incompatible_workers_cannot_claim_and_wrong_worker_cannot_read(setup, auth):
    client, store, _, clip = setup
    first, _ = pair_worker(client)
    second, _ = pair_worker(client, {"engines": ["resize"], "encoders": ["hevc_cpu"]})
    store.add_job(clip.name, Recipe().model_dump(), inspect_source(clip))
    assert store.claim(store.worker(second["token"]), 30) is None
    claimed = store.claim(store.worker(first["token"]), 30)
    response = client.get(
        f"/api/worker/jobs/{claimed['id']}/source",
        headers={"Authorization": f"Bearer {second['token']}", "X-Job-Lease": claimed["lease"]},
    )
    assert response.status_code == 409


def test_actual_worker_streams_processes_returns_and_cleans_scratch(setup, auth, tmp_path):
    client, store, _, clip = setup
    credentials, _ = pair_worker(client)
    recipe = Recipe(scale=1, denoise=True, sharpen=True, preview_seconds=5).model_dump()
    store.add_job(clip.name, recipe, inspect_source(clip))
    worker_info = store.worker(credentials["token"])
    claim = store.claim(worker_info, 90)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / ".popcorn-scratch").write_text("test-drive")
    worker = Worker("http://testserver", tmp_path / "worker-state", scratch)
    worker.reserve = 0
    worker.token = credentials["token"]

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app),
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {worker.token}"},
        ) as remote:
            await worker.run_job(remote, claim, 1)

    asyncio.run(run())
    result = store.job(claim["id"])
    assert result["status"] == "completed", result["error"]
    assert list(scratch.iterdir()) == [scratch / ".popcorn-scratch"]
    (scratch / ".popcorn-scratch").unlink()
    try:
        worker.storage()
        raise AssertionError("Missing drive must stop processing")
    except ValueError:
        pass
