import subprocess

import pytest
from fastapi.testclient import TestClient

from popcorn_sr.config import Settings
from popcorn_sr.server import create_app


@pytest.fixture
def setup(tmp_path):
    library, output = tmp_path / "library", tmp_path / "output"
    library.mkdir()
    output.mkdir()
    clip = library / "sample.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=128x96:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "1",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-y",
            str(clip),
        ],
        check=True,
    )
    cfg = Settings(
        tmp_path / "state",
        library,
        output,
        "test-access-key-32-characters-long",
        lease_seconds=4,
        reserve_bytes=0,
    )
    app = create_app(cfg)
    with TestClient(app) as client:
        yield client, app.state.store, cfg, clip


@pytest.fixture
def auth(setup):
    client, _, cfg, _ = setup
    client.post("/api/login", json={"username": "admin", "password": "admin"}).raise_for_status()
    client.post("/api/account/password", json={"username": "admin", "password": cfg.admin_token}).raise_for_status()
    return client


def pair_worker(client, caps=None):
    code = client.post("/api/pair-codes").json()["code"]
    payload = {
        "code": code,
        "name": "Test worker",
        "capabilities": caps or {"engines": ["resize"], "encoders": ["h264_cpu"]},
        "scratch": {"path": "/scratch", "free_bytes": 10000000},
    }
    response = client.post("/api/workers/pair", json=payload)
    assert response.status_code == 200
    return response.json(), payload
