"""Real manager pairing, CPU encode checks and native process cancellation."""

import asyncio
import json
import os
import sys
import threading
import time
from types import SimpleNamespace

import httpx
import pytest

from popcorn_sr import db as db_module
from popcorn_sr.engines import detect_capabilities, run_check
from popcorn_sr.media import inspect_source
from popcorn_sr.models import Recipe
from popcorn_sr.scratch import atomic_private_json, initialize
from popcorn_sr.worker import Worker
from tests.conftest import pair_worker


def make_worker(client, tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    initialize(scratch)
    worker = Worker("http://testserver", tmp_path / "worker-state", scratch, "Pairing test")
    worker.reserve = 0
    monkeypatch.setattr(worker, "client", lambda: httpx.AsyncClient(
        transport=httpx.ASGITransport(app=client.app), base_url=worker.manager,
        headers={"Authorization": f"Bearer {worker.token}"} if worker.token else {},
    ))
    heartbeat, monitor = worker.initialization_heartbeat, worker.monitor_storage
    monkeypatch.setattr(worker, "initialization_heartbeat", lambda client, finished: heartbeat(client, finished, .03))
    monkeypatch.setattr(worker, "monitor_storage", lambda: monitor(.03))
    return worker


async def until(condition, timeout=5):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("Condition was not reached")
        await asyncio.sleep(.01)


def test_unpaired_client_omits_empty_authorization_header(tmp_path):
    worker = Worker("http://testserver", tmp_path / "state", tmp_path / "scratch")
    async def run():
        async with worker.client() as client:
            assert "Authorization" not in client.headers
        worker.token = "saved-worker-token"
        async with worker.client() as client:
            assert client.headers["Authorization"] == "Bearer saved-worker-token"
    asyncio.run(run())


def test_code_consumed_before_slow_checks_with_live_status_then_real_cpu_ready(setup, auth, tmp_path, monkeypatch):
    client, store, _, clip = setup
    worker = make_worker(client, tmp_path, monkeypatch)
    code = store.pair_code()
    started, release = threading.Event(), threading.Event()

    def delayed_checks(folder, stopped):
        started.set()
        while not release.wait(.01):
            if stopped.is_set():
                raise ValueError("Stopped")
        return detect_capabilities(folder, stopped)

    monkeypatch.setattr("popcorn_sr.worker.detect_capabilities", delayed_checks)

    async def run():
        task = asyncio.create_task(worker.connect(code))
        try:
            await until(started.is_set)
            saved = json.loads(worker.credential_file.read_text())
            assert saved["worker_id"] == worker.worker_id and saved["token"] == worker.token
            assert worker.credential_file.stat().st_mode & 0o777 == 0o600
            initial = store.workers()[0]
            assert initial["online"] and initial["capabilities"]["initialization"] == "checking"
            assert not initial["capabilities"]["encoders"]
            job = store.add_job(clip.name, Recipe(scale=1).model_dump(), inspect_source(clip))
            assert store.claim(store.worker(worker.token), 90) is None
            # Advance the manager's clock past code expiry and the offline limit.
            now = time.time() + 601
            monkeypatch.setattr(db_module, "time", SimpleNamespace(time=lambda: now))
            await until(lambda: store.workers()[0]["last_seen"] == now)
            assert store.workers()[0]["online"]
            with pytest.raises(ValueError, match="expired or was already used"):
                store.pair(code, "Duplicate", {}, {})
            assert store.job(job["id"])["status"] == "queued"
            release.set()
            await asyncio.wait_for(task, 30)
            ready = store.workers()[0]
            assert ready["id"] == initial["id"]
            assert ready["capabilities"]["initialization"] == "ready"
            assert "h264_cpu" in ready["capabilities"]["encoders"]
            assert store.claim(store.worker(worker.token), 90)["id"] == job["id"]
            assert not list(worker.scratch.glob("capability-check-*"))
        finally:
            release.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())


@pytest.mark.parametrize("phase", ["checking", "failed", "unexpected"])
def test_unready_worker_cannot_claim_even_with_stale_verified_caps(setup, auth, phase):
    client, store, _, clip = setup
    credentials, _ = pair_worker(client, {
        "initialization": phase, "engines": ["resize"], "encoders": ["h264_cpu"],
    })
    job = store.add_job(clip.name, Recipe(scale=1).model_dump(), inspect_source(clip))
    assert store.claim(store.worker(credentials["token"]), 90) is None
    assert store.job(job["id"])["status"] == "queued"


@pytest.mark.parametrize("kind", ["missing", "invalid", "expired", "used", "revoked"])
def test_bad_pairing_never_starts_processing_checks(setup, auth, tmp_path, monkeypatch, kind):
    client, store, _, _ = setup
    worker = make_worker(client, tmp_path, monkeypatch)
    monkeypatch.setattr("popcorn_sr.worker.detect_capabilities", lambda *args: pytest.fail("Unauthenticated GPU check"))
    code = None if kind == "missing" else "invalid-code"
    if kind in {"expired", "used"}:
        code = store.pair_code()
        if kind == "expired":
            with store.connect() as connection:
                connection.execute("UPDATE pair_codes SET expires=0")
        else:
            store.pair(code, "Already paired", {}, {})
    if kind == "revoked":
        credentials, _ = pair_worker(client)
        atomic_private_json(worker.credential_file, credentials | {"manager": worker.manager})
        assert client.post(f"/api/workers/{credentials['worker_id']}/revoke").status_code == 200
    message = "not paired" if kind == "missing" else "revoked" if kind == "revoked" else "invalid, expired or already used"
    with pytest.raises(ValueError, match=message):
        asyncio.run(worker.connect(code))
    assert not list(worker.scratch.glob("capability-check-*"))


def test_saved_pairing_rechecks_real_encoding_without_a_new_code(setup, auth, tmp_path, monkeypatch):
    client, store, _, _ = setup
    worker = make_worker(client, tmp_path, monkeypatch)
    credentials, _ = pair_worker(client)
    atomic_private_json(worker.credential_file, credentials | {"manager": worker.manager})
    asyncio.run(worker.connect())
    assert worker.worker_id == credentials["worker_id"]
    assert len(store.workers()) == 1
    assert worker.capabilities["initialization"] == "ready"
    assert "h264_cpu" in worker.capabilities["encoders"]
    assert not list(worker.scratch.glob("capability-check-*"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX process group cancellation")
@pytest.mark.parametrize("failure", ["cancel", "drive", "revoke"])
def test_startup_failure_stops_real_child_group_before_reporting(setup, auth, tmp_path, monkeypatch, failure):
    client, store, _, _ = setup
    worker = make_worker(client, tmp_path, monkeypatch)
    marker = (worker.scratch / ".popcorn-scratch").read_bytes()
    pidfile = tmp_path / "process.pid"
    exited = threading.Event()

    def slow_check(folder, stopped):
        program = 'import os,sys,time; open(sys.argv[1],"w").write(str(os.getpid())); time.sleep(60)'
        try:
            assert not run_check([sys.executable, "-c", program, str(pidfile)], timeout=60, scratch=folder, stopped=stopped)
            raise ValueError("Worker initialization stopped.")
        finally:
            exited.set()

    monkeypatch.setattr("popcorn_sr.worker.detect_capabilities", slow_check)

    async def run():
        task = asyncio.create_task(worker.connect(store.pair_code()))
        try:
            await until(pidfile.exists)
            pid = int(pidfile.read_text())
            os.kill(pid, 0)
            if failure == "cancel":
                task.cancel()
                expected, message = asyncio.CancelledError, None
            elif failure == "drive":
                (worker.scratch / ".popcorn-scratch").unlink()
                expected, message = ValueError, "not ready"
            else:
                client.post(f"/api/workers/{worker.worker_id}/revoke")
                expected, message = ValueError, "revoked"
            with pytest.raises(expected, match=message):
                await asyncio.wait_for(task, 5)
            assert exited.is_set()
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
            if failure == "drive":
                # An unavailable drive must never be followed for cleanup.
                assert list(worker.scratch.glob("capability-check-*"))
                assert store.workers()[0]["scratch"]["available"] is False
            else:
                assert not list(worker.scratch.glob("capability-check-*"))
            if failure != "revoke":
                assert store.workers()[0]["capabilities"]["initialization"] == "failed"
                assert not store.workers()[0]["capabilities"]["encoders"]
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            (worker.scratch / ".popcorn-scratch").write_bytes(marker)

    asyncio.run(run())
