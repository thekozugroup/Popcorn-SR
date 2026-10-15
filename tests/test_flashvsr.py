"""Media-safety contracts; these tests do not establish AI/GPU execution."""

import hashlib
import os
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from popcorn_sr import flashvsr


def test_variable_picture_clock_is_exact_and_bounded():
    clock = flashvsr.PictureClock(Fraction(1, 1000))
    expected = []
    timestamp = 741
    # A long variable-rate stream must not retain its complete timeline.
    for _group in range(1000):
        for offset in (0, 19, 63, 81):
            clock.push(timestamp + offset, Fraction(1, 1000))
            expected.append(timestamp + offset - 741)
        for _ in range(4):
            assert clock.take() == expected.pop(0)
        timestamp += 120
    clock.finish({"frames": 4000, "last_frame_time": Fraction(timestamp - 120 + 81 - 741, 1000)})
    assert clock.peak == 4


@pytest.mark.parametrize("case", ["missing", "duplicate", "backwards", "off_clock", "extra", "lost"])
def test_reject_changed_picture_timeline(case):
    clock = flashvsr.PictureClock(Fraction(1, 1000))
    clock.push(20, Fraction(1, 1000))
    clock.take()
    with pytest.raises(ValueError):
        if case == "missing":
            clock.push(None, None)
        elif case in ("duplicate", "backwards"):
            clock.push(20 if case == "duplicate" else 19, Fraction(1, 1000))
        elif case == "off_clock":
            clock.push(1, Fraction(1, 3))
        elif case == "extra":
            clock.take()
        else:
            clock.push(53, Fraction(1, 1000))
            clock.finish({"frames": 2, "last_frame_time": Fraction(33, 1000)})


def test_reject_unbounded_model_lookahead():
    clock = flashvsr.PictureClock(Fraction(1, 1000))
    with pytest.raises(ValueError, match="bounded"):
        for timestamp in range(66):
            clock.push(timestamp, Fraction(1, 1000))


def test_private_caches_removed_and_environment_restored(tmp_path, monkeypatch):
    monkeypatch.setenv("TRITON_CACHE_DIR", "previous-driver-cache")
    before = dict(os.environ)
    with pytest.raises(RuntimeError), flashvsr.job_cache(tmp_path):
        folder = os.environ["TRITON_CACHE_DIR"]
        assert folder != "previous-driver-cache"
        assert os.environ["HF_HUB_OFFLINE"] == "1"
        (Path(folder) / "generated-cache.bin").write_bytes(b"owned cache")
        raise RuntimeError("model failed")
    assert dict(os.environ) == before
    assert not list(tmp_path.iterdir())


def test_existing_result_or_original_cannot_be_overwritten(tmp_path, monkeypatch):
    original = tmp_path / "original.mkv"
    original.write_bytes(b"original")
    monkeypatch.setattr(flashvsr, "_render", lambda _: pytest.fail("Existing path reached the encoder"))
    with pytest.raises(FileExistsError):
        flashvsr.render(SimpleNamespace(input=original, output=original))
    assert original.read_bytes() == b"original"


def test_failed_render_removes_only_owned_result(tmp_path, monkeypatch):
    original = tmp_path / "original.mkv"
    original.write_bytes(b"keep original")
    result = tmp_path / "result.mkv"

    def fail(args):
        args.output.write_bytes(b"partial output")
        raise ValueError("invalid pictures")

    monkeypatch.setattr(flashvsr, "_render", fail)
    with pytest.raises(ValueError, match="invalid pictures"):
        flashvsr.render(SimpleNamespace(input=original, output=result))
    assert original.read_bytes() == b"keep original"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["original.mkv"]


def test_concurrent_output_is_preserved(tmp_path, monkeypatch):
    result = tmp_path / "result.mkv"

    def substitute(args):
        args.output.write_bytes(b"validated result")
        result.write_bytes(b"replacement")

    monkeypatch.setattr(flashvsr, "_render", substitute)
    with pytest.raises(FileExistsError):
        flashvsr.render(SimpleNamespace(output=result))
    assert result.read_bytes() == b"replacement"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["result.mkv"]


def test_resident_weight_hook_restored_after_exception():
    def original(*args):
        raise AssertionError("CPU offload should not execute")

    module = SimpleNamespace(_offload_dit=original)
    with pytest.raises(RuntimeError), flashvsr.resident_weights(module):
        state = SimpleNamespace(attention_cache_offload_layers=(), attention_cache_transfer_stream=None)
        module._offload_dit(None, state, SimpleNamespace(type="cuda"))
        with pytest.raises(ValueError):
            module._offload_dit(None, state, SimpleNamespace(type="cpu"))
        raise RuntimeError("decoder failed")
    assert module._offload_dit is original


def test_reject_modified_checkpoint_and_runtime(tmp_path, monkeypatch):
    (tmp_path / ".popcorn-revision").write_text(flashvsr.RUNTIME_REVISION)
    model = tmp_path / "model.safetensors"
    model.write_bytes(b"verified example")
    monkeypatch.setattr(flashvsr, "MODEL_HASHES", {model.name: hashlib.sha256(model.read_bytes()).hexdigest()})
    flashvsr.verify_runtime(tmp_path, tmp_path)
    model.write_bytes(b"modified example")
    with pytest.raises(ValueError, match="checksum"):
        flashvsr.verify_runtime(tmp_path, tmp_path)
    (tmp_path / ".popcorn-revision").write_text("different upstream API")
    with pytest.raises(ValueError, match="revision"):
        flashvsr.verify_runtime(tmp_path, tmp_path)


@pytest.mark.parametrize("dimensions,padded", [((1440, 1080), (1536, 1152)), ((1920, 1080), (1920, 1152)), ((1080, 1920), (1152, 1920))])
def test_dimensions_are_padded_instead_of_cropped(dimensions, padded):
    assert flashvsr.padded_size(*dimensions) == padded


@pytest.mark.parametrize("dimensions", [(0, 1080), (1920, 1079), (True, 128), (7682, 2160)])
def test_invalid_dimensions_rejected(dimensions):
    with pytest.raises(ValueError):
        flashvsr.padded_size(*dimensions)


def test_restoration_requires_verified_codec_and_cannot_combine_unverified_stages():
    from popcorn_sr.dlss import compatible_recipe
    from popcorn_sr.models import Recipe

    recipe = Recipe(engine="flashvsr", encoder="nvidia").model_dump()
    caps = {"engines": ["flashvsr"], "encoders": ["h264_nvidia", "hevc_nvidia", "h264_cpu"]}
    assert not compatible_recipe(recipe, caps)
    caps["flashvsr"] = {"codecs": ["h264"]}
    assert compatible_recipe(recipe, caps)
    for changes in ({"codec": "hevc"}, {"encoder": "cpu"}, {"hdr": True}, {"frame_generation": True}):
        assert not compatible_recipe(recipe | changes, caps)


def test_adapter_uses_exact_size_paths_and_codec_without_shell(tmp_path, monkeypatch):
    from popcorn_sr.engines import adapter_command
    from popcorn_sr.models import Recipe

    monkeypatch.setenv("POPCORN_FLASHVSR_ROOT", "/opt/flash runtime")
    monkeypatch.setenv("POPCORN_FLASHVSR_MODELS", "/models/flash")
    command = adapter_command("flashvsr", tmp_path / "a ; file.mkv", tmp_path / "b.mkv",
                              Recipe(engine="flashvsr", encoder="nvidia", scale=3, codec="av1").model_dump(),
                              {"width": 640, "height": 480})
    assert command[1:3] == ["-m", "popcorn_sr.flashvsr"]
    for key, value in {"--width": "1920", "--height": "1440", "--codec": "av1", "--runtime": "/opt/flash runtime"}.items():
        assert command[command.index(key) + 1] == value
    assert str(tmp_path / "a ; file.mkv") in command


def test_model_install_rejects_corruption_and_cleans_partial_download(tmp_path, monkeypatch):
    import io

    from popcorn_sr import restoration_assets as assets

    target = tmp_path / "model"
    monkeypatch.setattr(assets.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"wrong"))
    expected = hashlib.sha256(b"verified").hexdigest()
    with pytest.raises(ValueError, match="checksum"):
        assets.download("https://example.invalid/model", target, expected)
    assert not list(tmp_path.iterdir())
    target.write_bytes(b"existing different model")
    with pytest.raises(ValueError, match="refusing to replace"):
        assets.download("https://example.invalid/model", target, expected)
    assert target.read_bytes() == b"existing different model"
