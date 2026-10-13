import pytest

from popcorn_sr.models import Recipe
from popcorn_sr.storage_plan import estimate_scratch_bytes

CAPABILITIES = {"dlss_frame_generation": {"maximum_factor": 6}}
SOURCE = {"size": 10 * 1024**2, "width": 1920, "height": 1080, "duration": 7200, "frame_rate": "24000/1001"}


def test_generation_budget_accounts_for_lossless_video_and_preview_duration():
    recipe = Recipe(encoder="nvidia", scale=1, frame_generation=True, frame_rate="480").model_dump()
    full = estimate_scratch_bytes(SOURCE, recipe, CAPABILITIES)
    short = estimate_scratch_bytes(SOURCE, recipe | {"preview_seconds": 5}, CAPABILITIES)
    assert full > 1024**4  # A tiny compressed source does not imply a small 480-fps job.
    assert short < full / 1000
    assert estimate_scratch_bytes(SOURCE, recipe | {"frame_generation": False}, {}) == SOURCE["size"] * 4
    assert all(estimate_scratch_bytes(SOURCE, recipe | {"codec": codec}, CAPABILITIES) == full
               for codec in ("h264", "hevc", "av1"))


def test_generation_budget_tracks_actual_dlss_size_and_native_pass_rounding():
    recipe = Recipe(engine="dlss-sr", encoder="nvidia", frame_generation=True, frame_rate="480").model_dump()
    dlaa = estimate_scratch_bytes(SOURCE, recipe | {"dlss_mode": "dlaa"}, CAPABILITIES)
    quality = estimate_scratch_bytes(SOURCE, recipe | {"dlss_mode": "quality"}, CAPABILITIES)
    performance = estimate_scratch_bytes(SOURCE, recipe | {"dlss_mode": "performance"}, CAPABILITIES)
    assert dlaa < quality < performance
    assert estimate_scratch_bytes(SOURCE, recipe | {"frame_generation_mode": "cascade"}, CAPABILITIES) > performance
    with pytest.raises(ValueError, match="estimate generation storage"):
        estimate_scratch_bytes(SOURCE, recipe | {"frame_generation_mode": "native"}, CAPABILITIES)


def test_unknown_timing_or_unverified_native_limits_cannot_bypass_storage_planning():
    recipe = Recipe(encoder="nvidia", frame_generation=True).model_dump()
    for invalid in (SOURCE | {"frame_rate": "0/0"}, SOURCE | {"duration": float("nan")}, SOURCE | {"duration": -1}):
        with pytest.raises(ValueError, match="estimate generation storage"):
            estimate_scratch_bytes(invalid, recipe, CAPABILITIES)
    with pytest.raises(ValueError, match="estimate generation storage"):
        estimate_scratch_bytes(SOURCE, recipe, {})
