"""Resolution rules use real source headers and reject unsupported workers."""

import asyncio

import httpx
import pytest
from pydantic import ValidationError

from popcorn_sr.dlss import compatible_recipe
from popcorn_sr.media import probe, sha256
from popcorn_sr.models import Recipe
from popcorn_sr.resolution import resolve, target_dimensions, tier
from popcorn_sr.scratch import initialize
from popcorn_sr.worker import Worker
from tests.conftest import pair_worker


@pytest.mark.parametrize(("size", "category", "target", "output"), [
    ((1280, 720), "720", 1080, (1920, 1080)),
    ((1920, 1080), "1080", 2160, (3840, 2160)),
    ((1920, 800), "1080", 2160, (3840, 1600)),
    ((720, 1280), "720", 1080, (1080, 1920)),
    ((2560, 1440), "1440", 2160, (3840, 2160)),
    ((2048, 1080), "1440", 2160, (3840, 2024)),
])
def test_classify_and_fit_without_stretching(size, category, target, output):
    source = dict(zip(("width", "height"), size, strict=True))
    assert tier(*size) == category
    assert target_dimensions(source, target) == output


def test_native_resolution_rules_choose_verified_modes_and_preserve_explicit_choices():
    caps = {"engines": ["dlss-sr"], "encoders": ["h264_nvidia"], "resolution_rules": True,
            "dlss_sr": {"resolution_targets": True, "settings": [["quality", "default"], ["performance", "default"]],
                        "temporal_qualities": ["low"]}}
    recipe = Recipe(engine="dlss-sr", encoder="nvidia", temporal_quality="low",
                    resolution_rules={"720": "1080", "1080": "2160"}).model_dump()
    workers = [{"capabilities": caps}]
    for source, mode in [({"width": 1280, "height": 720}, "quality"), ({"width": 1920, "height": 1080}, "performance")]:
        resolved = resolve(recipe, source, workers)
        assert resolved["dlss_mode"] == mode
        assert compatible_recipe(resolved, caps)
        assert not compatible_recipe(resolved, caps | {"resolution_rules": False})
    with pytest.raises(ValueError, match="No verified DLSS mode"):
        resolve(recipe | {"dlss_preset": "k"}, {"width": 1280, "height": 720}, workers)
    with pytest.raises(ValueError, match="No verified DLSS mode"):
        resolve(recipe | {"resolution_rules": {"720": "4320"}}, {"width": 1280, "height": 720}, workers)


def test_bad_downscale_unknown_and_combined_controls_are_rejected():
    for rules in ({"1080": "720"}, {"other": "1080"}, {"540": "1080"}):
        with pytest.raises(ValidationError):
            Recipe(resolution_rules=rules)
    with pytest.raises(ValidationError):
        Recipe(engine="rtx-vsr", resolution_rules={"720": "1080"}, output_width=1920, output_height=1080)
    assert resolve(Recipe(resolution_rules={"720": "1080"}).model_dump(), {"width": 1920, "height": 1080}, [])["scale"] == 1


def test_metadata_cache_is_authenticated_bounded_read_only_and_invalidated(setup, auth, monkeypatch):
    client, _, cfg, source = setup
    import popcorn_sr.server as server

    calls = []
    def metadata(path):
        calls.append(path)
        return {"width": 128, "height": 96, "codec": "h264"}
    monkeypatch.setattr(server, "picture_metadata", metadata)
    before = sha256(source)
    for _ in range(2):
        assert client.get("/api/library/metadata", params={"path": source.name}).json()["codec"] == "h264"
    assert len(calls) == 1 and sha256(source) == before
    source.touch()
    assert client.get("/api/library/metadata", params={"path": source.name}).status_code == 200
    assert len(calls) == 2
    for path in ("../sample.mkv", str(source), "missing.mkv"):
        assert client.get("/api/library/metadata", params={"path": path}).status_code == 400
    link = cfg.library / "escape.mkv"
    link.symlink_to(cfg.output / "outside.mkv")
    assert client.get("/api/library/metadata", params={"path": link.name}).status_code == 400
    client.cookies.clear()
    assert client.get("/api/library/metadata", params={"path": source.name}).status_code == 401
    assert len(calls) == 2


def test_rules_preview_and_saved_full_run_preserve_target_and_original(setup, auth, tmp_path):
    client, store, cfg, source = setup
    before = sha256(source)
    caps = {"engines": ["resize"], "encoders": ["h264_cpu"], "resolution_rules": True}
    credentials, _ = pair_worker(client, caps)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    initialize(scratch)
    worker = Worker("http://testserver", tmp_path / "worker-state", scratch)
    worker.token, worker.worker_id, worker.reserve = credentials["token"], credentials["worker_id"], 0
    body = {"path": source.name, "recipe": Recipe(resolution_rules={"480": "720"}, preview_seconds=5,
                                                preview_frame_time=.25).model_dump()}
    response = client.post("/api/jobs", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["planned_output"] == {"width": 960, "height": 720}
    async def deliver():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app), base_url="http://testserver",
                                    headers={"Authorization": f"Bearer {worker.token}"}) as remote:
            await worker.run_job(remote, store.claim(store.worker(worker.token), 90), 1)
    asyncio.run(deliver())
    result = store.job(response.json()["id"])
    assert result["status"] == "completed", result["error"]
    full = client.post(f"/api/jobs/{result['id']}/full")
    assert full.status_code == 200 and full.json()["recipe"]["target_resolution"] == 720
    asyncio.run(deliver())
    completed = store.job(full.json()["id"])
    assert completed["status"] == "completed", completed["error"]
    info = probe(cfg.output / completed["result"]["path"])
    assert (info["width"], info["height"], info["audio_streams"]) == (960, 720, 1)
    assert sha256(source) == before and not list(scratch.glob("job-*"))
    store.touch(worker.worker_id, caps | {"resolution_rules": False}, {"path": str(scratch), "free_bytes": 1e9})
    assert client.post("/api/jobs", json=body).status_code == 400
