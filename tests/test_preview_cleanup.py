import json
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from popcorn_sr.models import Recipe


def saved_job(setup, *, preview=True):
    client, store, cfg, clip = setup
    recipe = Recipe(scale=1, preview_seconds=5 if preview else 0).model_dump()
    response = client.post("/api/jobs", json={"path": clip.name, "recipe": recipe})
    assert response.status_code == 200
    job = response.json()
    folder = cfg.output / recipe["output_directory"]
    folder.mkdir(exist_ok=True)
    file = folder / f"sample.{'preview' if preview else 'sr'}.{job['id']}.mkv"
    file.write_bytes(b"generated output owned by this job")
    result = {"path": file.relative_to(cfg.output).as_posix(), "width": 128, "height": 96}
    with store.connect() as db:
        db.execute("UPDATE jobs SET status='completed',result=? WHERE id=?", (json.dumps(result), job["id"]))
    return job, file


def test_delete_preview_removes_only_owned_file_and_entry(setup, auth):
    client, store, cfg, clip = setup
    preview, file = saved_job(setup)
    full, full_file = saved_job(setup, preview=False)
    original, full_bytes = clip.read_bytes(), full_file.read_bytes()
    neighbor = file.parent / "unrelated.preview.mkv"
    neighbor.write_bytes(b"not this job")
    assert client.delete(f"/api/jobs/{preview['id']}/preview").status_code == 200
    assert not file.exists() and store.job(preview["id"]) is None
    assert store.job(full["id"]) and full_file.read_bytes() == full_bytes
    assert clip.read_bytes() == original and neighbor.read_bytes() == b"not this job"
    assert client.get(f"/api/jobs/{preview['id']}/download").status_code == 404
    assert client.get(f"/api/jobs/{preview['id']}/frame?side=enhanced").status_code == 409
    assert client.post(f"/api/jobs/{preview['id']}/full").status_code == 409
    assert client.delete(f"/api/jobs/{preview['id']}/preview").status_code == 404


def test_preview_delete_requires_owner_and_refuses_full_or_active_jobs(setup, auth):
    client, store, _, clip = setup
    full, file = saved_job(setup, preview=False)
    assert client.delete(f"/api/jobs/{full['id']}/preview").status_code == 409
    assert file.exists()
    preview, file = saved_job(setup)
    for status in ("queued", "running"):
        with store.connect() as db:
            db.execute("UPDATE jobs SET status=? WHERE id=?", (status, preview["id"]))
        assert client.delete(f"/api/jobs/{preview['id']}/preview").status_code == 409
        assert file.exists() and store.job(preview["id"])
    client.cookies.clear()
    assert client.delete(f"/api/jobs/{preview['id']}/preview").status_code == 401
    assert file.exists() and clip.exists()


@pytest.mark.parametrize("case", ["leaf-link", "parent-link", "foreign-path", "traversal", "directory"])
def test_preview_delete_rejects_path_replacements_and_keeps_record(setup, auth, case):
    client, store, cfg, clip = setup
    preview, file = saved_job(setup)
    original = clip.read_bytes()
    if case == "leaf-link":
        file.unlink()
        file.symlink_to(clip)
    elif case == "parent-link":
        file.unlink()
        file.parent.rmdir()
        file.parent.symlink_to(cfg.library, target_is_directory=True)
    elif case == "directory":
        file.unlink()
        file.mkdir()
    else:
        result = {"path": "../library/sample.mkv" if case == "traversal" else "enhanced/unrelated.mkv"}
        with store.connect() as db:
            db.execute("UPDATE jobs SET result=? WHERE id=?", (json.dumps(result), preview["id"]))
    assert client.delete(f"/api/jobs/{preview['id']}/preview").status_code == 409
    assert store.job(preview["id"]) and clip.read_bytes() == original


def test_preview_delete_handles_missing_result_and_hardlinks_without_deleting_source(setup, auth):
    client, store, _, clip = setup
    preview, file = saved_job(setup)
    file.unlink()
    assert client.delete(f"/api/jobs/{preview['id']}/preview").status_code == 200
    preview, file = saved_job(setup)
    file.unlink()
    original = clip.read_bytes()
    os.link(clip, file)
    assert client.delete(f"/api/jobs/{preview['id']}/preview").status_code == 200
    assert clip.read_bytes() == original
    for status in ("failed", "cancelled"):
        job = store.add_job(clip.name, Recipe(preview_seconds=5).model_dump(), {})
        with store.connect() as db:
            db.execute("UPDATE jobs SET status=? WHERE id=?", (status, job["id"]))
        assert client.delete(f"/api/jobs/{job['id']}/preview").status_code == 200


def test_concurrent_preview_deletion_is_serialized(setup, auth):
    client, store, _, clip = setup
    preview, file = saved_job(setup)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.delete(f"/api/jobs/{preview['id']}/preview").status_code, range(2)))
    assert sorted(results) == [200, 404]
    assert not file.exists() and store.job(preview["id"]) is None and clip.exists()


def test_deletion_failure_preserves_preview_and_queue_entry(setup, auth, monkeypatch):
    client, store, _, clip = setup
    preview, file = saved_job(setup)
    unlink = os.unlink

    def denied(path, *args, **kwargs):
        if path == file.name:
            raise PermissionError("read-only output")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "unlink", denied)
    assert client.delete(f"/api/jobs/{preview['id']}/preview").status_code == 409
    assert file.exists() and store.job(preview["id"]) and clip.exists()


def test_unavailable_output_preserves_record_for_later_cleanup(setup, auth):
    client, store, cfg, _ = setup
    preview, file = saved_job(setup)
    moved = cfg.output.with_name("detached-output")
    cfg.output.rename(moved)
    assert client.delete(f"/api/jobs/{preview['id']}/preview").status_code == 409
    assert store.job(preview["id"])
    moved.rename(cfg.output)
    assert file.exists()
    assert client.delete(f"/api/jobs/{preview['id']}/preview").status_code == 200
