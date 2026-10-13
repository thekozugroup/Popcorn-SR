import asyncio
import importlib.util
import json
import time
import uuid
from pathlib import Path

import httpx
import pytest

from popcorn_sr.updates import WorkerUpdates
from popcorn_sr.worker import Worker
from tests.conftest import pair_worker

SPEC = importlib.util.spec_from_file_location("worker_updater", Path(__file__).parents[1] / "scripts/update-worker.py")
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)


def test_authenticated_request_blocks_next_claim_and_ack_is_scoped(auth, setup):
    _, store, _, _ = setup
    paired, _ = pair_worker(auth, {"engines": ["resize"], "encoders": ["h264_cpu"], "updates": {"enabled": True}})
    other, _ = pair_worker(auth)
    identity = paired["worker_id"]
    auth.post("/api/jobs", json={"path": "sample.mkv", "worker_id": identity, "recipe": {"scale": 1}}).raise_for_status()
    first = auth.post(f"/api/workers/{identity}/update").json()["request_id"]
    assert auth.post(f"/api/workers/{identity}/update").json()["request_id"] == first
    auth.headers["Authorization"] = "Bearer " + paired["token"]
    assert auth.post("/api/worker/claim").json()["job"] is None
    caps = {"engines": ["resize"], "encoders": ["h264_cpu"], "updates": {"enabled": True, "request_id": first}}
    auth.headers["Authorization"] = "Bearer " + other["token"]
    auth.post("/api/worker/status", json={"capabilities": caps, "scratch": {}}).raise_for_status()
    assert store.update_request(identity) == first
    auth.headers["Authorization"] = "Bearer " + paired["token"]
    assert auth.post("/api/worker/status", json={"capabilities": caps, "scratch": {}}).json()["update_request"] is None
    assert auth.post("/api/worker/claim").json()["job"] is not None
    auth.headers.pop("Authorization")
    assert auth.post(f"/api/workers/{identity}/update").status_code == 401


def test_unmanaged_and_revoked_update_requests_rejected(auth):
    worker, _ = pair_worker(auth)
    assert auth.post(f"/api/workers/{worker['worker_id']}/update").status_code == 409
    assert auth.post("/api/workers/nonexistent/update").status_code == 409
    auth.post(f"/api/workers/{worker['worker_id']}/revoke").raise_for_status()
    assert auth.post(f"/api/workers/{worker['worker_id']}/update").status_code == 409


def test_worker_control_is_bounded_and_requires_live_controller(tmp_path):
    updates = WorkerUpdates(tmp_path)
    assert not updates.status()["enabled"]
    (tmp_path / "controller.json").write_text(json.dumps({"updated_at": time.time(), "automatic": True}))
    assert updates.status()["enabled"]
    identity = updates.request()
    assert str(uuid.UUID(identity)) == identity
    before = (tmp_path / "request.json").stat().st_mtime_ns
    assert updates.request(identity) == identity
    assert (tmp_path / "request.json").stat().st_mtime_ns == before
    with pytest.raises(ValueError):
        updates.request("../../docker.sock")
    (tmp_path / "controller.json").write_text('x' * 40000)
    assert not updates.status()["enabled"]
    (tmp_path / "drain.json").write_text('{"id":"test-drain"}')
    updates.runtime({"initialization": "ready"}, idle=True)
    runtime = json.loads((tmp_path / "runtime.json").read_text())
    assert runtime["idle"] and runtime["drain_id"] == "test-drain"
    assert updates.status()["draining"]


def test_worker_drain_never_claims_and_releases_after_host_finishes(tmp_path, monkeypatch):
    control = tmp_path / "control"
    control.mkdir()
    monkeypatch.setenv("POPCORN_UPDATE_DIRECTORY", str(control))
    worker = Worker("http://manager", tmp_path / "state", tmp_path)
    worker.capabilities = {"initialization": "ready", "engines": ["resize"]}
    calls = []
    request_id = str(uuid.uuid4())
    host.write(control / "drain.json", {"id": "drain"})

    async def connect(*args):
        pass

    async def recover(*args):
        pass

    def respond(request):
        calls.append(request.url.path)
        if request.url.path.endswith("status"):
            return httpx.Response(200, json={"ok": True, "update_request": request_id})
        raise RuntimeError("claimed after drain cleared")

    async def sleep(*args):
        assert calls == ["/api/worker/status"]
        assert host.read(control / "runtime.json")["idle"]
        (control / "drain.json").unlink()

    monkeypatch.setattr(worker, "connect", connect)
    monkeypatch.setattr(worker, "recover_scratch", recover)
    monkeypatch.setattr(worker, "storage", lambda: {})
    monkeypatch.setattr(worker, "client", lambda: httpx.AsyncClient(base_url="http://manager", transport=httpx.MockTransport(respond)))
    monkeypatch.setattr("popcorn_sr.worker.asyncio.sleep", sleep)
    with pytest.raises(RuntimeError, match="claimed after drain cleared"):
        asyncio.run(worker._run())
    assert calls == ["/api/worker/status", "/api/worker/status", "/api/worker/claim"]
    assert host.read(control / "request.json")["id"] == request_id


@pytest.fixture
def updater(tmp_path):
    control = tmp_path / "control"
    control.mkdir()
    compose, environment = tmp_path / "worker.yaml", tmp_path / "worker.env"
    compose.write_text("services: {}")
    environment.write_text("POPCORN_PAIR_CODE=private-preserve\nPOPCORN_NGX_IMAGE=previous\nSCRATCH_PATH=/external/drive\n")
    config = tmp_path / "update.json"
    host.write(config, {"control": str(control), "role": "ngx", "compose": str(compose),
                        "environment": str(environment), "project": "update-test", "automatic": True})
    return host.Updater(config)


def test_controller_waits_for_current_worker_idle_and_preserves_secrets(updater, monkeypatch):
    old, new = "sha256:" + "a" * 64, "sha256:" + "b" * 64
    reference = updater.repository + "@sha256:" + "c" * 64
    tx = {"id": "drain", "request_id": None, "old_image": old, "old_version": "0.4.0", "image": new,
          "reference": reference, "version": "0.4.1", "revision": "d" * 40, "phase": "waiting"}
    host.write(updater.state, {"transaction": tx})
    current = {"Image": old, "Config": {"Hostname": "current-worker"}, "State": {"Running": True}}
    monkeypatch.setattr(updater, "container", lambda: current)
    host.write(updater.control / "runtime.json", {"updated_at": time.time(), "container": "current-worker", "idle": False})
    replaced = []
    monkeypatch.setattr(updater, "recreate", replaced.append)
    updater.run()
    assert not replaced
    assert host.read(updater.control / "status.json")["state"] == "waiting"
    host.write(updater.control / "runtime.json", {"updated_at": time.time(), "container": "wrong-worker", "idle": True, "drain_id": "drain"})
    updater.run()
    assert not replaced
    caps = {"initialization": "ready", "engines": ["resize", "dlss-sr"], "encoders": ["av1_nvidia"]}
    host.write(updater.control / "runtime.json", {"updated_at": time.time(), "container": "current-worker", "idle": True, "drain_id": "drain", "capabilities": caps})
    monkeypatch.setattr(updater, "validate", lambda image, target, previous: None)
    updater.run()
    assert replaced == [reference]
    assert not (updater.control / "drain.json").exists()
    env = Path(updater.config["environment"]).read_text()
    assert "POPCORN_PAIR_CODE=private-preserve\n" in env and "SCRATCH_PATH=/external/drive\n" in env
    assert "POPCORN_NGX_IMAGE=" + reference in env


def test_controller_failed_candidate_restores_exact_previous_image(updater, monkeypatch):
    old, new = "sha256:" + "a" * 64, "sha256:" + "b" * 64
    tx = {"id": "drain", "request_id": None, "old_image": old, "old_version": "0.4.0", "image": new,
          "reference": updater.repository + "@sha256:" + "c" * 64, "version": "0.4.1", "revision": "d" * 40,
          "phase": "validating", "previous_features": {"engines": ["dlss-sr"]}}
    host.write(updater.state, {"transaction": tx})
    monkeypatch.setattr(updater, "container", lambda: {})
    replaced = []
    monkeypatch.setattr(updater, "recreate", replaced.append)

    def validate(image, target, features):
        if image == new:
            raise ValueError("runtime failed")

    monkeypatch.setattr(updater, "validate", validate)
    updater.run()
    assert replaced == [tx["reference"], old]
    assert host.read(updater.control / "status.json")["state"] == "rolled_back"
    assert "POPCORN_NGX_IMAGE=previous\n" in Path(updater.config["environment"]).read_text()
    assert not (updater.control / "drain.json").exists()


def test_feature_gate_rejects_lost_encoder_sr_and_frame_generation():
    caps = {"initialization": "ready", "engines": ["dlss-sr"], "encoders": ["av1_nvidia"],
            "resolution_rules": True,
            "dlss_sr": {"settings": [["performance", "default"]], "resolution_targets": True, "temporal_qualities": ["high"]},
            "dlss_frame_generation": {"settings": [["cascade", "high"]], "maximum_factor": 6}}
    assert host.retains_features(caps, caps)
    for key in ("encoders", "engines", "dlss_sr", "dlss_frame_generation"):
        assert not host.retains_features(caps, caps | {key: [] if key in {"encoders", "engines"} else {}})
    assert not host.retains_features(caps, caps | {"resolution_rules": False})
    for field in ("resolution_targets", "temporal_qualities"):
        assert not host.retains_features(caps, caps | {"dlss_sr": caps["dlss_sr"] | {field: False if field == "resolution_targets" else []}})


def test_controller_rejects_worker_writable_configuration(updater):
    path = Path(updater.config["compose"])
    path.chmod(0o666)
    with pytest.raises(ValueError, match="another user"):
        host.Updater(updater.config_path)


@pytest.mark.parametrize("value", [0, 1201, "1200", True])
def test_controller_rejects_invalid_validation_budget(updater, value):
    host.write(updater.config_path, updater.config | {"validation_seconds": value})
    with pytest.raises(ValueError, match="validation timeout"):
        host.Updater(updater.config_path)
