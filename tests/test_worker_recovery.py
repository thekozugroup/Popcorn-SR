"""Exercise drive replacement and real process lifetimes, without GPU substitutes."""

import asyncio
import json
import os
import signal
import subprocess
import sys

import httpx
import pytest

from popcorn_sr.engines import run_check
from popcorn_sr.media import inspect_source
from popcorn_sr.models import Recipe
from popcorn_sr.scratch import atomic_private_json, initialize
from popcorn_sr.worker import Worker, exclusive_file
from tests.conftest import pair_worker


def claimed_worker(setup, auth, tmp_path):
    client, store, _, clip = setup
    credentials, _ = pair_worker(client)
    store.add_job(clip.name, Recipe(scale=1).model_dump(), inspect_source(clip))
    claim = store.claim(store.worker(credentials["token"]), 90)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    initialize(scratch)
    worker = Worker("http://testserver", tmp_path / "worker-state", scratch)
    worker.reserve = 0
    worker.token = credentials["token"]
    worker.worker_id = credentials["worker_id"]
    worker.storage()
    return client, store, worker, claim


def remote(client, worker):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=client.app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {worker.token}"},
    )


def owned_folder(worker, claim):
    folder = worker.scratch / f"job-{claim['id']}-{claim['lease'][:8]}"
    folder.mkdir()
    atomic_private_json(
        folder / ".popcorn-job.json",
        {
            "version": 1,
            "worker_id": worker.worker_id,
            "job_id": claim["id"],
            "lease": claim["lease"],
            "drive_id": worker.drive_id,
        },
    )
    (folder / "source.mkv").write_bytes(b"owned interrupted transfer")
    return folder


def test_scratch_identity_persists_and_copied_marker_fails(tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    initialize(scratch)
    state = tmp_path / "state"
    first = Worker("http://testserver", state, scratch)
    observed = first.storage()
    restarted = Worker("http://testserver", state, scratch)
    assert restarted.storage()["drive_id"] == observed["drive_id"]
    assert (state / "scratch.json").stat().st_mode & 0o777 == 0o600
    marker = json.loads((scratch / ".popcorn-scratch").read_text())
    marker["drive_id"] = "replaced-drive"
    atomic_private_json(scratch / ".popcorn-scratch", marker)
    with pytest.raises(ValueError, match="changed since pairing"):
        Worker("http://testserver", state, scratch).storage()
    marker["drive_id"] = observed["drive_id"]
    atomic_private_json(scratch / ".popcorn-scratch", marker)
    monkeypatch.setattr("popcorn_sr.scratch.filesystem_id", lambda path: "fs:replacement")
    with pytest.raises(ValueError, match="filesystem changed"):
        restarted.storage()


def test_legacy_marker_upgrade_and_malformed_marker_rejected(tmp_path):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    marker = scratch / ".popcorn-scratch"
    marker.write_text("existing-drive")
    assert initialize(scratch)["drive_id"] == "existing-drive"
    marker.write_text('{"version":1,"drive_id":123}')
    with pytest.raises(ValueError, match="not supported"):
        initialize(scratch)
    marker.unlink()
    outside = tmp_path / "outside"
    outside.write_text("keep")
    marker.symlink_to(outside)
    with pytest.raises(ValueError, match="not ready"):
        initialize(scratch)
    assert outside.read_text() == "keep"


def test_existing_job_folder_is_preserved(setup, auth, tmp_path):
    client, store, worker, claim = claimed_worker(setup, auth, tmp_path)
    folder = worker.scratch / f"job-{claim['id']}-{claim['lease'][:8]}"
    folder.mkdir()
    (folder / "unknown-file").write_text("keep")

    async def run():
        async with remote(client, worker) as api:
            await worker.run_job(api, claim, 1)

    asyncio.run(run())
    assert (folder / "unknown-file").read_text() == "keep"
    assert store.job(claim["id"])["status"] == "failed"


@pytest.mark.skipif(os.name != "posix", reason="POSIX file/process ownership contract")
def test_recovery_waits_for_inherited_child_lock(setup, auth, tmp_path):
    client, store, worker, claim = claimed_worker(setup, auth, tmp_path)
    folder = owned_folder(worker, claim)
    lock = exclusive_file(folder / ".popcorn-active.lock")
    fd = lock.__enter__()
    child = subprocess.Popen(
        [sys.executable, "-c", 'import time; print("ready", flush=True); time.sleep(60)'],
        pass_fds=(fd,),
        stdout=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        assert child.stdout.readline() == b"ready\n"
        lock.__exit__(None, None, None)  # Simulate loss of the parent, child remains alive.
        unknown = worker.scratch / "job-unknown"
        unknown.mkdir()
        (unknown / ".popcorn-job.json").write_text("[]")
        link = worker.scratch / "job-symlink"
        link.symlink_to(unknown, target_is_directory=True)

        async def recover():
            async with remote(client, worker) as api:
                await worker.recover_scratch(api)

        asyncio.run(recover())
        assert folder.exists()
        assert store.job(claim["id"])["status"] == "running"
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=5)
        asyncio.run(recover())
        assert not folder.exists()
        assert store.job(claim["id"])["status"] == "failed"
        assert unknown.exists() and link.is_symlink()
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        child.stdout.close()


@pytest.mark.skipif(os.name != "posix", reason="POSIX file/process ownership contract")
def test_cancel_real_worker_encode_stops_process_and_cleans(setup, auth, tmp_path, monkeypatch):
    client, store, worker, claim = claimed_worker(setup, auth, tmp_path)
    started = asyncio.Event()
    processes = []
    actual_spawn = asyncio.create_subprocess_exec

    async def slow_spawn(*command, **kwargs):
        # Use actual FFmpeg decoding/encoding; realtime pacing guarantees the
        # cancellation happens during work instead of after a tiny clip finishes.
        if command[0] == "ffmpeg":
            index = command.index("-i")
            command = (*command[:index], "-re", *command[index:])
        process = await actual_spawn(*command, **kwargs)
        processes.append(process)
        started.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", slow_spawn)

    async def run():
        async with remote(client, worker) as api:
            job = asyncio.create_task(worker.run_job(api, claim, 1))
            await asyncio.wait_for(started.wait(), 5)
            job.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(job, 5)

    asyncio.run(run())
    assert processes and all(p.returncode is not None for p in processes)
    assert store.job(claim["id"])["status"] == "failed"
    assert not list(worker.scratch.glob("job-*"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX process group cancellation")
def test_capability_timeout_terminates_descendants(tmp_path):
    pidfile = tmp_path / "child.pid"
    parent = (
        "import subprocess,sys,time; "
        'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
        'open(sys.argv[1],"w").write(str(child.pid)); time.sleep(60)'
    )
    assert not run_check([sys.executable, "-c", parent, str(pidfile)], timeout=1, scratch=tmp_path)
    assert pidfile.exists()
    pid = int(pidfile.read_text())
    # Linux may briefly retain a killed orphan as a zombie until init reaps it.
    status = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
    ).stdout.strip()
    assert not status or status.startswith("Z"), status


@pytest.mark.skipif(os.name != "posix", reason="POSIX inherited ownership lock")
def test_ai_encoder_retains_job_lock_after_parent_releases(tmp_path, monkeypatch):
    from fractions import Fraction

    import av

    from popcorn_sr.video_pipe import encoded_video

    lock_path = tmp_path / "job.lock"
    lock = exclusive_file(lock_path)
    fd = lock.__enter__()
    monkeypatch.setenv("POPCORN_ACTIVE_JOB_FD", str(fd))
    with encoded_video(
        tmp_path / "result.mkv",
        64,
        48,
        Fraction(24),
        Fraction(1, 24),
        ["-c:v", "libx264", "-pix_fmt", "yuv420p"],
    ) as (output, stream):
        lock.__exit__(None, None, None)
        # The actual FFmpeg process now owns the only remaining inherited FD.
        with pytest.raises(BlockingIOError):
            with exclusive_file(lock_path):
                pytest.fail("Active encoder lost its scratch ownership lock")
        frame = av.VideoFrame(64, 48, "rgb24")
        frame.planes[0].update(bytes(frame.planes[0].buffer_size))
        frame.pts, frame.time_base = 0, Fraction(1, 24)
        for packet in stream.encode(frame):
            output.mux(packet)
    with exclusive_file(lock_path):
        pass  # The encoder finished and released its inherited descriptor.


@pytest.mark.skipif(os.name != "posix", reason="POSIX immediate process termination")
def test_cancel_does_not_wait_for_unreachable_manager(setup, auth, tmp_path, monkeypatch):
    client, _, worker, claim = claimed_worker(setup, auth, tmp_path)
    started = asyncio.Event()
    stopped = asyncio.Event()
    processes = []
    actual_spawn = asyncio.create_subprocess_exec

    async def slow_spawn(*command, **kwargs):
        index = command.index("-i")
        command = (*command[:index], "-re", *command[index:])
        process = await actual_spawn(*command, **kwargs)
        processes.append(process)
        started.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", slow_spawn)

    async def run():
        async with remote(client, worker) as api:
            original_post = api.post

            async def stalled_post(url, **kwargs):
                if url.endswith("/fail"):
                    assert processes and all(p.returncode is not None for p in processes)
                    stopped.set()
                    await asyncio.sleep(60)
                return await original_post(url, **kwargs)

            monkeypatch.setattr(api, "post", stalled_post)
            job = asyncio.create_task(worker.run_job(api, claim, 1))
            await asyncio.wait_for(started.wait(), 5)
            job.cancel()
            await asyncio.wait_for(stopped.wait(), 1)
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(job, 4)

    asyncio.run(run())
    assert not list(worker.scratch.glob("job-*"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX immediate process termination")
@pytest.mark.parametrize("fault", ["full", "replaced"])
def test_storage_failure_stops_real_process_without_waiting_for_heartbeat(setup, auth, tmp_path, monkeypatch, fault):
    client, store, worker, claim = claimed_worker(setup, auth, tmp_path)
    started, stopped = asyncio.Event(), asyncio.Event()
    processes, broken = [], False
    original_marker = json.loads((worker.scratch / ".popcorn-scratch").read_text())
    actual_storage, actual_spawn = worker.storage, asyncio.create_subprocess_exec
    worker.reserve = 1
    unknown = worker.scratch / "job-unknown"
    unknown.mkdir()
    (unknown / "keep").write_text("unrelated")

    def storage():
        observed = actual_storage()
        if broken and fault == "full":
            observed["free_bytes"] = 0
        return observed

    async def spawn(*command, **kwargs):
        process = await actual_spawn(*command, **kwargs)
        processes.append(process)
        started.set()
        return process

    async def held_processing(api, job, folder):
        await worker.process([sys.executable, "-c", "import time; time.sleep(60)"], folder, 60)

    monkeypatch.setattr(worker, "storage", storage)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(worker, "perform", held_processing)

    async def run():
        nonlocal broken
        async with remote(client, worker) as api:
            original_post = api.post

            async def stalled_post(url, **kwargs):
                if url.endswith("/fail"):
                    assert processes and all(p.returncode is not None for p in processes)
                    stopped.set()
                    await asyncio.sleep(60)
                return await original_post(url, **kwargs)

            monkeypatch.setattr(api, "post", stalled_post)
            job = asyncio.create_task(worker.run_job(api, claim, 60))
            await asyncio.wait_for(started.wait(), 5)
            broken = True
            if fault == "replaced":
                atomic_private_json(worker.scratch / ".popcorn-scratch", original_marker | {"drive_id": "replacement"})
            await asyncio.wait_for(stopped.wait(), 2)
            await asyncio.wait_for(job, 3)
        # Reconnect after failure reporting was unavailable. Restore the original
        # owned marker; recovery must leave unrelated folders untouched.
        broken = False
        atomic_private_json(worker.scratch / ".popcorn-scratch", original_marker)
        async with remote(client, worker) as api:
            response = await api.post(f"/api/worker/jobs/{claim['id']}/fail", json={"lease": claim["lease"], "error": "Storage interrupted"})
            response.raise_for_status()
            await worker.recover_scratch(api)

    asyncio.run(run())
    assert store.job(claim["id"])["status"] == "failed"
    assert [path.name for path in worker.scratch.glob("job-*")] == ["job-unknown"]
    assert (unknown / "keep").read_text() == "unrelated"


def test_generation_rejects_insufficient_lossless_space_before_downloading(setup, auth, tmp_path, monkeypatch):
    client, store, worker, claim = claimed_worker(setup, auth, tmp_path)
    claim["recipe"] = Recipe(encoder="nvidia", frame_generation=True, scale=2).model_dump()
    worker.capabilities = {"dlss_frame_generation": {"maximum_factor": 6}}
    observed = worker.storage()
    monkeypatch.setattr(worker, "storage", lambda: observed | {"free_bytes": claim["source"]["size"] * 4 + 1})

    async def forbidden_transfer(*args):
        pytest.fail("Generation downloaded a source despite inadequate lossless storage")

    monkeypatch.setattr(worker, "perform", forbidden_transfer)

    async def run():
        async with remote(client, worker) as api:
            await worker.run_job(api, claim, 1)

    asyncio.run(run())
    assert store.job(claim["id"])["status"] == "failed"
    assert "free temporary storage" in store.job(claim["id"])["error"]
    assert not list(worker.scratch.glob("job-*"))
