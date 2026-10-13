from fractions import Fraction

import numpy as np
import pytest

from popcorn_sr.dlss import compatible_recipe
from popcorn_sr.dlss_sr import MotionEstimator, driver_scratch
from popcorn_sr.media import dimensions
from popcorn_sr.models import Recipe


@pytest.mark.parametrize("quality", ["low", "medium", "high"])
def test_backward_flow_and_scene_cut(quality):
    import cv2

    # Actual dense optical flow: translate repeatable texture right by four pixels.
    rng = np.random.default_rng(491)
    texture = rng.integers(0, 256, size=(192, 256), dtype=np.uint8)
    texture = cv2.GaussianBlur(texture, (3, 3), 0.5)
    previous = np.repeat(texture[:, :, None], 3, axis=2)
    current = np.roll(previous, 4, axis=1)
    estimator = MotionEstimator(quality)
    flow, reset = estimator.estimate(previous, Fraction(1), Fraction(1, 24))
    assert reset and not flow.any()
    flow, reset = estimator.estimate(current, Fraction(25, 24), Fraction(1, 24))
    assert not reset
    center = flow[40:-40, 40:-40]
    assert float(np.median(center[:, :, 0])) == pytest.approx(-4, abs=0.5)
    assert float(np.median(center[:, :, 1])) == pytest.approx(0, abs=0.3)
    assert flow.flags.c_contiguous and flow.dtype == np.float32
    flow, reset = estimator.estimate(np.zeros_like(current), Fraction(26, 24), Fraction(1, 24))
    assert reset and not flow.any()
    flow, reset = estimator.estimate(current, Fraction(4), Fraction(1, 24))
    assert reset and not flow.any()
    with pytest.raises(ValueError, match="timestamps"):
        estimator.estimate(current, Fraction(4), Fraction(1, 24))


def test_recipe_dimensions_and_verified_claim_settings():
    source = {"width": 1920, "height": 1080}
    for mode, expected in {
        "dlaa": (1920, 1080), "quality": (2880, 1620), "balanced": (3312, 1864),
        "performance": (3840, 2160), "ultra-performance": (5760, 3240),
    }.items():
        recipe = Recipe(engine="dlss-sr", encoder="nvidia", dlss_mode=mode).model_dump()
        assert dimensions(source, recipe) == expected
    legacy = Recipe(engine="dlss-sr", encoder="nvidia", scale=3).model_dump()
    caps = {"engines": ["dlss-sr"], "encoders": ["h264_nvidia"]}
    assert compatible_recipe(legacy, caps)
    advanced = legacy | {"dlss_mode": "quality", "dlss_preset": "k"}
    assert not compatible_recipe(advanced, caps)
    caps["dlss_sr"] = {"settings": [["quality", "k"]], "temporal_qualities": ["high"]}
    assert compatible_recipe(advanced, caps)
    assert not compatible_recipe(advanced | {"dlss_preset": "m"}, caps)
    assert not compatible_recipe(advanced | {"temporal_quality": "low"}, caps)
    assert not compatible_recipe(advanced | {"codec": "hevc"}, caps)


def test_driver_cache_cleanup_after_failure(tmp_path, monkeypatch):
    import os

    monkeypatch.setenv("HOME", "/original-home")
    monkeypatch.delenv("CUDA_CACHE_PATH", raising=False)
    with pytest.raises(RuntimeError):
        with driver_scratch(tmp_path / "result.mkv") as scratch:
            from pathlib import Path

            path = Path(scratch)
            assert path.stat().st_mode & 0o777 == 0o700
            assert os.environ["HOME"] == scratch == os.environ["CUDA_CACHE_PATH"]
            (path / "owned-cache").write_bytes(b"temporary")
            raise RuntimeError("simulated render failure")
    assert not path.exists()
    assert os.environ["HOME"] == "/original-home"
    assert "CUDA_CACHE_PATH" not in os.environ


def test_manager_rejects_unverified_dlss_settings_and_claims_only_matching_workers(setup, auth):
    from tests.conftest import pair_worker

    client, store, _, _ = setup
    recipe = Recipe(engine="dlss-sr", encoder="nvidia", dlss_mode="quality", dlss_preset="k").model_dump()
    queued = {"path": "sample.mkv", "recipe": recipe}
    assert client.post("/api/jobs", json=queued).status_code == 400
    caps = {"engines": ["dlss-sr"], "encoders": ["h264_nvidia"]}
    old, _ = pair_worker(client, caps)
    assert client.post("/api/jobs", json=queued | {"worker_id": old["worker_id"]}).status_code == 400
    supported, _ = pair_worker(client, caps | {"dlss_sr": {
        "settings": [["quality", "k"]], "temporal_qualities": ["high"],
    }})
    response = client.post("/api/jobs", json=queued)
    assert response.status_code == 200
    assert store.claim(store.worker(old["token"]), 60) is None
    claimed = store.claim(store.worker(supported["token"]), 60)
    assert claimed["id"] == response.json()["id"] and claimed["recipe"]["dlss_preset"] == "k"
