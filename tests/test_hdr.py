"""Real CPU encoding proves transport/precision, never NVIDIA conversion."""

import subprocess
from fractions import Fraction

import av
import numpy as np
import pytest

from popcorn_sr.hdr import HDR10_SIGNALING, RGB10_COLOR, hdr_encoding_options, packed_hdr_frame, validate_hdr
from popcorn_sr.media import probe
from popcorn_sr.video_pipe import encoded_video


def words(width, height):
    red = np.broadcast_to(np.arange(width, dtype=np.uint32), (height, width)) % 1024
    green = np.broadcast_to((np.arange(height, dtype=np.uint32) * 1023 // (height - 1))[:, None], (height, width))
    blue = 1023 - red
    return red | (green << 10) | (blue << 20) | np.uint32(3 << 30)


def frames(path, options, *, width=1024, height=64, end=None):
    values = words(width, height)
    with encoded_video(path, width, height, Fraction(25), Fraction(1, 1000), options,
                       end_time=end, final_frame_time=Fraction(1, 5) if end else None,
                       input_pix_fmt="gbrp10le", color_metadata=RGB10_COLOR) as (output, stream):
        for pts in (0, 40, 120, 200):
            frame = packed_hdr_frame(values)
            frame.pts, frame.time_base = pts, Fraction(1, 1000)
            for packet in stream.encode(frame):
                output.mux(packet)
    return values


def test_all_1024_rgb_levels_survive_packed_pipe_with_padding(tmp_path):
    path = tmp_path / "ten-bit-transport.nut"
    # Width 1026 exercises row padding while containing every 10-bit red level.
    expected = frames(path, ["-c:v", "ffv1", "-level", "3", "-pix_fmt", "gbrp10le"], width=1026)
    with av.open(path) as container:
        decoded = list(container.decode(video=0))
        assert len(decoded) == 4
        assert [float(frame.pts * frame.time_base) for frame in decoded] == pytest.approx([0, .04, .12, .2], abs=.001)
        for frame in decoded:
            assert frame.format.name == "gbrp10le"
            # FFmpeg's planar order is G, B, R. Compare actual decoded words.
            for plane, shift in zip(frame.planes, (10, 20, 0), strict=True):
                pixels = np.frombuffer(plane, dtype="<u2").reshape(frame.height, plane.line_size // 2)[:, :frame.width]
                np.testing.assert_array_equal(pixels, (expected >> shift) & 1023)
            assert len(np.unique(pixels)) == 1024
    assert set(tmp_path.iterdir()) == {path}
    rejected = tmp_path / "unsupported-packed.mkv"
    with pytest.raises(ValueError, match="packed HDR is unsupported"):
        with encoded_video(rejected, 1026, 64, Fraction(25), Fraction(1, 1000),
                           ["-c:v", "ffv1"], input_pix_fmt="x2bgr10le"):
            pytest.fail("Packed HDR must be rejected before encoder startup.")
    assert not rejected.exists()


@pytest.mark.parametrize("codec", ["hevc", "av1"])
@pytest.mark.parametrize("end", [Fraction(21, 100), Fraction(36, 100)])
def test_real_ten_bit_exports_preserve_hdr_signaling_and_variable_timing(tmp_path, codec, end):
    path = tmp_path / (codec + ".mkv")
    # CPU diagnostic fixtures only. Actual TrueHDR always requires NVENC.
    options = ["-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "lossless=1:pools=2:frame-threads=1:log-level=error"] if codec == "hevc" else [
        "-c:v", "libsvtav1", "-preset", "12", "-crf", "18", "-svtav1-params", "lp=2",
    ]
    options += ["-bf", "0", "-pix_fmt", "yuv420p10le", *HDR10_SIGNALING]
    frames(path, options, end=end)
    info = probe(path)
    validate_hdr(info)
    assert info["codec"] == codec
    assert info["duration"] == pytest.approx(float(end), abs=.001)
    with av.open(path) as container:
        decoded = list(container.decode(video=0))
        assert len(decoded) == 4
        assert [float(frame.pts * frame.time_base) for frame in decoded] == pytest.approx([0, .04, .12, .2], abs=.001)
        plane = decoded[0].planes[0]
        luma = np.frombuffer(plane, dtype="<u2").reshape(64, plane.line_size // 2)[:, :1024]
        assert len(np.unique(luma)) > 256
        assert len(np.unique(luma & 3)) == 4
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], check=True, capture_output=True)
    with pytest.raises(ValueError, match="10-bit"):
        validate_hdr(info | {"bit_depth": 8})
    for field in ("color_primaries", "color_transfer", "color_space", "color_range"):
        with pytest.raises(ValueError, match="signaling"):
            validate_hdr(info | {field: "unknown"})


def test_hdr_rejects_rgb8_and_h264_before_processing():
    with pytest.raises(ValueError, match="H.265 or AV1"):
        hdr_encoding_options("h264", 23)
    with pytest.raises(ValueError, match="uint32"):
        packed_hdr_frame(np.zeros((4, 4), dtype=np.uint8))
    assert hdr_encoding_options("hevc", 23)[-len(HDR10_SIGNALING):] == HDR10_SIGNALING


def test_hdr_queue_requires_exact_verified_pipeline_and_bounds(setup, auth):
    from popcorn_sr.dlss import compatible_recipe
    from popcorn_sr.models import Recipe
    from tests.conftest import pair_worker

    client, store, _, clip = setup
    recipe = Recipe(hdr=True, codec="hevc", encoder="nvidia", scale=1).model_dump()
    caps = {"engines": ["resize"], "encoders": ["h264_nvidia", "hevc_nvidia", "av1_nvidia"]}
    old, _ = pair_worker(client, caps)
    body = {"path": clip.name, "recipe": recipe}
    assert client.post("/api/jobs", json=body).status_code == 400
    supported, _ = pair_worker(client, caps | {"rtx_hdr": {"pipelines": [["resize", False, "hevc"]]}})
    assert client.post("/api/jobs", json=body | {"worker_id": old["worker_id"]}).status_code == 400
    for changes in ({"codec": "h264"}, {"encoder": "cpu"}, {"codec": "av1"}, {"frame_generation": True}):
        assert client.post("/api/jobs", json=body | {"recipe": recipe | changes}).status_code == 400
    for key, value in (("hdr_contrast", -1), ("hdr_saturation", 201), ("hdr_middle_gray", 9), ("hdr_luminance", 2001)):
        assert client.post("/api/jobs", json=body | {"recipe": recipe | {key: value}}).status_code == 422
    queued = client.post("/api/jobs", json=body)
    assert queued.status_code == 200
    assert store.claim(store.worker(old["token"]), 60) is None
    assert store.claim(store.worker(supported["token"]), 60)["id"] == queued.json()["id"]
    verified = caps | {"rtx_hdr": {"pipelines": [["resize", False, "hevc"]]}}
    assert compatible_recipe(recipe, verified)
    assert not compatible_recipe(recipe, verified | {"initialization": "checking"})
    assert not compatible_recipe(recipe, verified | {"rtx_hdr": {"pipelines": []}})


@pytest.mark.parametrize("codec", ["hevc", "av1"])
@pytest.mark.parametrize("generation", [False, True])
def test_hdr_pipeline_delivery_keeps_media_and_saved_settings_with_cpu_diagnostics(setup, auth, tmp_path, monkeypatch, codec, generation):
    """Exercise delivery and stage ordering. SDK calls are explicit CPU fixtures."""
    import asyncio
    import json
    from pathlib import Path

    import httpx

    from popcorn_sr.frame_generation import cadence, source_timeline
    from popcorn_sr.media import ffmpeg_command, inspect_source, sha256
    from popcorn_sr.models import Recipe
    from popcorn_sr.worker import Worker
    from tests.conftest import pair_worker

    client, store, cfg, clip = setup
    original = sha256(clip)
    caps = {"engines": ["resize"], "encoders": [f"{codec}_nvidia"],
            "rtx_hdr": {"pipelines": [["resize", generation, codec]]},
            "dlss_frame_generation": {"upscalers": ["resize"], "settings": [["auto", "high"]], "maximum_factor": 6}}
    credentials, _ = pair_worker(client, caps)
    recipe = Recipe(scale=1, hdr=True, codec=codec, encoder="nvidia", preview_seconds=5,
                    hdr_luminance=1000, hdr_contrast=85, hdr_saturation=110,
                    hdr_middle_gray=45, hdr_debanding=False, frame_generation=generation).model_dump()
    queued = client.post("/api/jobs", json={"path": clip.name, "recipe": recipe})
    assert queued.status_code == 200, queued.text
    claim = store.claim(store.worker(credentials["token"]), 90)
    # Independently reject an SDR return before it reaches the output mount.
    sdr = tmp_path / "sdr-return.mkv"
    subprocess.run(ffmpeg_command(clip, sdr, recipe | {"encoder": "cpu", "hdr": False}, inspect_source(clip)), check=True, capture_output=True)
    rejected = client.put(f"/api/worker/jobs/{claim['id']}/result", content=sdr.read_bytes(), headers={
        "Authorization": f"Bearer {credentials['token']}", "X-Job-Lease": claim["lease"], "X-Output-SHA256": sha256(sdr),
    })
    assert rejected.status_code == 400 and "10-bit" in rejected.json()["detail"]
    assert not list(cfg.output.rglob("*.mkv"))
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / ".popcorn-scratch").write_text("hdr-delivery-fixture")
    worker = Worker("http://testserver", tmp_path / "worker", scratch)
    worker.reserve, worker.token = 0, credentials["token"]
    worker.capabilities = caps
    actual_process, stages = worker.process, []
    monkeypatch.setenv("POPCORN_NVIDIA_HDR", "1")
    monkeypatch.setenv("POPCORN_NGX_DLSSG_LIBRARY", "/fixture/not-loaded")
    monkeypatch.setenv("POPCORN_NGX_RUNTIME", "/fixture/not-loaded")

    async def diagnostic_process(command, folder, duration):
        stages.append((worker.status["stage"], command))
        if "popcorn_sr.frame_generation" in command:
            assert command[command.index("--codec") + 1] == "ffv1"
            timing = source_timeline(command[command.index("--input") + 1])
            count = cadence(command[command.index("--input") + 1], command[command.index("--output") + 1],
                            Fraction(60), timing["duration"], "ffv1", 23)
            Path(command[command.index("--report") + 1]).write_text(json.dumps({
                "source_video_duration": str(timing["duration"]), "output_frames": count,
            }))
        elif "popcorn_sr.nvidia_hdr" in command:
            assert command[command.index("--luminance") + 1] == "1000" and "--debanding-off" in command
            incoming, returned = [command[command.index(flag) + 1] for flag in ("--input", "--output")]
            timing = source_timeline(incoming)
            end = Fraction(command[command.index("--end-time") + 1]) if "--end-time" in command else timing["duration"]
            opts = ["-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "pools=2:frame-threads=1:log-level=error"] if codec == "hevc" else [
                "-c:v", "libsvtav1", "-preset", "12", "-svtav1-params", "lp=2",
            ]
            opts += ["-bf", "0", "-pix_fmt", "yuv420p10le", *HDR10_SIGNALING]
            with av.open(incoming) as source:
                video = source.streams.video[0]
                with encoded_video(returned, video.width, video.height, timing["rate"], timing["time_base"], opts,
                                   end_time=end, final_frame_time=timing["last_frame_time"],
                                   input_pix_fmt="gbrp10le", color_metadata=RGB10_COLOR) as (output, stream):
                    first = None
                    for frame in source.decode(video):
                        first = frame.pts if first is None else first
                        # Synthetic precision fixture; never an NVIDIA conversion claim.
                        rgb = frame.to_ndarray(format="rgb24").astype(np.uint32) * 4
                        packed = rgb[:, :, 0] | (rgb[:, :, 1] << 10) | (rgb[:, :, 2] << 20)
                        result = packed_hdr_frame(packed)
                        result.pts, result.time_base = frame.pts - first, frame.time_base
                        for packet in stream.encode(result):
                            output.mux(packet)
        else:
            await actual_process(command, folder, duration)

    monkeypatch.setattr(worker, "process", diagnostic_process)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app), base_url="http://testserver",
                                     headers={"Authorization": f"Bearer {worker.token}"}) as remote:
            await worker.run_job(remote, claim, 1)

    asyncio.run(run())
    result = store.job(claim["id"])
    assert result["status"] == "completed", result["error"]
    validate_hdr(result["result"])
    assert sha256(clip) == original
    assert not list(scratch.glob("job-*"))
    assert [stage for stage, _ in stages] == ["Encoding video", *(["Generating DLSS frames"] if generation else []), "Converting to HDR", "Converting to HDR"]
    assert stages[0][1][stages[0][1].index("-c:v") + 1] == "ffv1"
    continued = client.post(f"/api/jobs/{claim['id']}/full")
    assert continued.status_code == 200, continued.text
    assert continued.json()["recipe"] == recipe | {"preview_seconds": 0}
    store.touch(credentials["worker_id"], caps | {"rtx_hdr": {"pipelines": []}})
    assert client.post(f"/api/jobs/{claim['id']}/full").status_code == 400
