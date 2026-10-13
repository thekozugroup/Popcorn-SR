"""CPU contract/timing fixtures. None of these asserts real NVIDIA VSR quality."""

import argparse
import json
import sys
from fractions import Fraction
from types import SimpleNamespace

import av
import cv2
import numpy as np
import pytest
from pydantic import ValidationError

from popcorn_sr.dlss import compatible_recipe
from popcorn_sr.engines import adapter_command
from popcorn_sr.media import dimensions, probe
from popcorn_sr.models import Recipe
from popcorn_sr.nvidia_vsr import QUALITY_NAMES, render, strength, validate_render, verify_settings
from popcorn_sr.video_pipe import encoded_video, encoding_options
from tests.conftest import pair_worker

CAPS = {
    "engines": ["rtx-vsr"],
    "encoders": ["h264_nvidia", "hevc_nvidia", "av1_nvidia"],
    "rtx_vsr": {
        "qualities": [1, 2, 3, 4],
        "strength": True,
        "custom_size": True,
        "codecs": ["h264", "hevc", "av1"],
        "lossless": True,
    },
}


def test_vsr_queue_claim_and_continuation_require_actual_settings_report(setup, auth):
    client, store, _, clip = setup
    old, _ = pair_worker(client, CAPS | {"rtx_vsr": {}})
    recipe = Recipe(
        engine="rtx-vsr",
        encoder="nvidia",
        vsr_quality=4,
        vsr_strength=0.6,
        output_width=264,
        output_height=200,
        preview_seconds=5,
    ).model_dump()
    body = {"path": clip.name, "recipe": recipe}
    assert client.post("/api/jobs", json=body).status_code == 400
    current, _ = pair_worker(client, CAPS)
    assert client.post("/api/jobs", json=body | {"worker_id": old["worker_id"]}).status_code == 400
    job = client.post("/api/jobs", json=body).json()
    assert job["recipe"] == recipe
    assert dimensions({"width": 128, "height": 96}, recipe) == (264, 200)
    assert store.claim(store.worker(old["token"]), 60) is None
    assert store.claim(store.worker(current["token"]), 60)["id"] == job["id"]
    for report in (
        {},
        CAPS["rtx_vsr"] | {"strength": False},
        CAPS["rtx_vsr"] | {"custom_size": False},
        CAPS["rtx_vsr"] | {"qualities": [1, 2, 3]},
        CAPS["rtx_vsr"] | {"codecs": ["hevc"]},
    ):
        assert not compatible_recipe(recipe, CAPS | {"rtx_vsr": report})
    with store.connect() as db:
        db.execute(
            "UPDATE jobs SET status='completed', result=? WHERE id=?",
            (json.dumps({"path": "fixture.mkv"}), job["id"]),
        )
    continued = client.post(f"/api/jobs/{job['id']}/full")
    assert continued.status_code == 200, continued.text
    assert continued.json()["recipe"] == recipe | {"preview_seconds": 0}
    for changes in (
        {"vsr_quality": 0},
        {"vsr_quality": 5},
        {"vsr_strength": 1.1},
        {"output_width": 265},
        {"output_height": None},
        {"output_width": 7688},
        {"engine": "resize"},
    ):
        assert client.post("/api/jobs", json=body | {"recipe": recipe | changes}).status_code == 422
    with pytest.raises(ValidationError):
        Recipe(engine="rtx-vsr", vsr_strength=float("nan"))
    for bad in ("nan", "inf", "-0.1", "1.1"):
        with pytest.raises(argparse.ArgumentTypeError):
            strength(bad)


def test_vsr_legacy_defaults_and_external_controls_are_not_silently_ignored(tmp_path, monkeypatch):
    source, output = tmp_path / "source.mkv", tmp_path / "output.mkv"
    recipe = Recipe(engine="rtx-vsr", encoder="nvidia").model_dump()
    info = {"width": 128, "height": 96}
    monkeypatch.setenv("POPCORN_NVIDIA_VFX", "1")
    command = adapter_command("rtx-vsr", source, output, recipe, info)
    assert command[command.index("--vsr-quality") + 1] == "3"
    monkeypatch.setenv("POPCORN_NVIDIA_VFX", "0")
    monkeypatch.setenv("POPCORN_FAST_RTXVSR", "/fixture/fast")
    command = adapter_command("rtx-vsr", source, output, recipe, info)
    assert command[command.index("--quality") + 1] == "ULTRA"
    with pytest.raises(ValueError, match="strength/lossless"):
        adapter_command("rtx-vsr", source, output, recipe | {"vsr_strength": 0.5}, info)
    monkeypatch.setenv("POPCORN_VSR_COMMAND", json.dumps(["/fixture/external", "{input}", "{output}"]))
    with pytest.raises(ValueError, match="does not accept"):
        adapter_command("rtx-vsr", source, output, recipe | {"vsr_quality": 2}, info)


class CPUTensor:
    """Small NumPy-only test double; deliberately cannot use CUDA or a model."""

    def __init__(self, values):
        self.values = np.asarray(values)

    @property
    def shape(self):
        return self.values.shape

    @property
    def dtype(self):
        return self.values.dtype

    def to(self, _):
        return self

    def permute(self, *axes):
        return CPUTensor(self.values.transpose(axes))

    def float(self):
        return CPUTensor(self.values.astype(np.float32))

    def div_(self, value):
        self.values /= value
        return self

    def contiguous(self):
        return self

    def clone(self):
        return CPUTensor(self.values.copy())

    def clamp(self, low, high):
        return CPUTensor(np.clip(self.values, low, high))

    def mul(self, value):
        return CPUTensor(self.values * value)

    def round(self):
        return CPUTensor(np.round(self.values))

    def byte(self):
        return CPUTensor(self.values.astype(np.uint8))

    def cpu(self):
        return self

    def numpy(self):
        return self.values


@pytest.mark.parametrize("failure", [None, "load", "shape", "nan"])
@pytest.mark.parametrize("codec", ["h264", "ffv1"])
def test_public_vsr_api_lifecycle_and_irregular_clock_using_explicit_cpu_double(
    tmp_path, monkeypatch, failure, codec
):
    import popcorn_sr.nvidia_vsr as adapter

    source, output = tmp_path / "source.mkv", tmp_path / ("result.nut" if codec == "ffv1" else "result.mkv")
    with encoded_video(
        source,
        128,
        96,
        Fraction(25),
        Fraction(1, 1000),
        encoding_options("ffv1", 23),
        end_time=Fraction(36, 100),
        final_frame_time=Fraction(1, 5),
    ) as (container, stream):
        for pts in (0, 40, 120, 200):
            frame = av.VideoFrame.from_ndarray(np.full((96, 128, 3), pts, dtype=np.uint8), format="rgb24")
            frame.pts, frame.time_base = pts, Fraction(1, 1000)
            for packet in stream.encode(frame):
                container.mux(packet)
    instances = []

    class FakeVSR:
        QualityLevel = {name: name for name in QUALITY_NAMES.values()}
        ImageEncoding = SimpleNamespace(RGB8="RGB8")

        def __init__(self, **kwargs):
            self.options, self.closed, self.is_loaded = kwargs, False, False
            instances.append(self)

        def load(self):
            if failure == "load":
                raise RuntimeError("fixture load failure")
            self.is_loaded = True

        def run(self, rgb, stream_ptr):
            assert stream_ptr == 0
            values = cv2.resize(
                rgb.values.transpose(1, 2, 0), (self.output_width, self.output_height)
            ).transpose(2, 0, 1)
            if failure == "shape":
                values = values[:, :-1, :]
            if failure == "nan":
                values[0, 0, 0] = np.nan
            return SimpleNamespace(image=CPUTensor(values))

        def close(self):
            self.closed = True

    monkeypatch.setitem(sys.modules, "nvvfx", SimpleNamespace(VideoSuperRes=FakeVSR))
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            float32=np.dtype("float32"),
            from_numpy=CPUTensor,
            from_dlpack=lambda image: image,
            isfinite=lambda tensor: np.isfinite(tensor.values),
            cuda=SimpleNamespace(
                is_available=lambda: True,
                set_device=lambda _: None,
                current_stream=lambda: SimpleNamespace(cuda_stream=0),
            ),
        ),
    )
    real_options = encoding_options
    monkeypatch.setattr(
        adapter,
        "encoding_options",
        lambda name, quality: (
            real_options(name, quality)
            if name == "ffv1"
            else [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-bf",
                "0",
                "-pix_fmt",
                "yuv420p",
            ]
        ),
    )
    args = SimpleNamespace(
        input=source,
        output=output,
        width=264,
        height=200,
        codec=codec,
        quality=23,
        vsr_quality=4,
        strength=0.6,
    )
    if failure:
        with pytest.raises(
            RuntimeError, match={"load": "load failure", "shape": "dimensions", "nan": "non-finite"}[failure]
        ):
            render(args)
    else:
        render(args)
        if codec != "ffv1":
            assert probe(output)["duration"] == pytest.approx(0.36, abs=0.001)
        with av.open(output) as container:
            assert [
                float(frame.pts * frame.time_base) for frame in container.decode(video=0)
            ] == pytest.approx([0, 0.04, 0.12, 0.2], abs=0.001)
        validate_render(source, output, 264, 200, codec)
    assert instances[0].options == {
        "device": 0,
        "quality": "ULTRA",
        "strength": 0.6,
        "image_encoding": "RGB8",
    }
    assert instances[0].closed


def test_vsr_report_retains_only_successful_codec_and_lossless_contracts(tmp_path, monkeypatch):
    import popcorn_sr.nvidia_vsr as adapter

    calls = []

    def diagnostic(args):
        calls.append((args.codec, args.vsr_quality, args.strength, args.width, args.height))
        if args.codec in {"av1", "ffv1"}:
            raise RuntimeError("explicit unavailable fixture")
        args.output.write_bytes(b"owned fixture")

    monkeypatch.setattr(adapter, "render", diagnostic)
    args = argparse.Namespace(
        input=tmp_path / "input.mkv",
        output=tmp_path / "output.mkv",
        width=512,
        height=288,
        codec="h264",
        quality=23,
        vsr_quality=3,
        strength=1.0,
        verify_codecs="h264,hevc,av1",
        verify_settings=tmp_path / "report.json",
    )
    verify_settings(args)
    report = json.loads(args.verify_settings.read_text())
    assert report == {
        "qualities": [1, 2, 3, 4],
        "strength": True,
        "custom_size": True,
        "codecs": ["h264", "hevc"],
        "lossless": False,
    }
    assert {item[1:3] for item in calls if item[0] == "hevc"} == {
        (level, amount) for level in range(1, 5) for amount in (0, 0.5, 1)
    }
    assert set(tmp_path.iterdir()) == {args.verify_settings}


def test_combined_vsr_requires_lossless_even_with_stale_pipeline_lists():
    caps = CAPS | {"rtx_hdr": {"pipelines": [["rtx-vsr", False, "hevc"]]},
                   "dlss_frame_generation": {"upscalers": ["rtx-vsr"], "settings": [["auto", "high"]]}}
    for extra in ({"hdr": True, "codec": "hevc"}, {"frame_generation": True}):
        recipe = Recipe(engine="rtx-vsr", encoder="nvidia", **extra).model_dump()
        assert compatible_recipe(recipe, caps)
        assert not compatible_recipe(recipe, caps | {"rtx_vsr": CAPS["rtx_vsr"] | {"lossless": False}})


def test_frame_controller_keeps_measured_end_after_nut_loses_final_duration(tmp_path, monkeypatch):
    """Real cadence/export with explicit native-call fixtures; no DLSSG pixels."""
    import shutil

    import popcorn_sr.frame_generation as controller

    source, output, report = tmp_path / "source.nut", tmp_path / "result.mkv", tmp_path / "timing.json"
    with encoded_video(source, 128, 96, Fraction(25), Fraction(1, 1000), encoding_options("ffv1", 23)) as (container, stream):
        for pts in (0, 40, 120, 200):
            frame = av.VideoFrame.from_ndarray(np.zeros((96, 128, 3), dtype=np.uint8), format="rgb24")
            frame.pts, frame.time_base = pts, Fraction(1, 1000)
            for packet in stream.encode(frame):
                container.mux(packet)
    assert controller.source_timeline(source)["duration"] == Fraction(24, 100)

    def native_fixture(command, **progress):
        if "--inspect-native" in command:
            return {"maximum_factor": 6}
        # Copy source frames: proves the controller contract, never generation.
        shutil.copyfile(command[command.index("--input") + 1], command[command.index("--output") + 1])
    monkeypatch.setattr(controller, "adapter_process", native_fixture)
    args = argparse.Namespace(input=str(source), output=str(output), library="not-loaded", runtime="not-loaded",
                              fps="60", mode="auto", temporal_quality="high", codec="ffv1", quality=23,
                              report=str(report), source_end_time=Fraction(36, 100))
    controller.render(args)
    timing = json.loads(report.read_text())
    assert timing["source_video_duration"] == "9/25"
    assert timing["output_frames"] == 22
    assert probe(output)["duration"] == pytest.approx(.36, abs=.001)
    with av.open(output) as returned:
        clocks = [float(frame.pts * frame.time_base) for frame in returned.decode(video=0)]
        assert clocks == pytest.approx([index / 60 for index in range(22)], abs=.001)
    with pytest.raises(ValueError, match="end must follow"):
        controller.render(argparse.Namespace(**(vars(args) | {"source_end_time": Fraction(1, 5)})))
    assert set(tmp_path.iterdir()) == {source, output, report}
