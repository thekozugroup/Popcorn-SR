"""Real color/pixel checks, independent of a GPU or an enhancement substitute."""

import json
import subprocess
from fractions import Fraction

import av
import numpy as np
import pytest

from popcorn_sr.frame_generation import cadence
from popcorn_sr.media import ffmpeg_command, probe, validate_output
from popcorn_sr.models import Recipe
from popcorn_sr.preview_sample import sample
from popcorn_sr.sdr import PROFILE_TAG, SDRColor, validate_sdr
from popcorn_sr.video_pipe import encoded_video, encoding_options


def read_rgb(path, matrix, range_name):
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-vf",
        f"scale=in_color_matrix={matrix}:in_range={range_name}:out_range=full:flags=bilinear",
        "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
    ])
    return np.frombuffer(raw, np.uint8).reshape(96, 256, 3)


def source_clip(path, matrix, range_name):
    # RGB patches with moderate, distinct chroma expose a wrong 601/709
    # conversion. The independent FFmpeg source specifies both conversion
    # and signaling; the code under test does not create the fixture.
    patches = np.array([[25, 160, 215], [205, 70, 35], [55, 185, 65], [160, 45, 185],
                        [35, 65, 190], [180, 155, 40], [45, 45, 45], [205, 205, 205]], np.uint8)
    rgb = np.broadcast_to(np.repeat(patches, 32, axis=0)[None], (96, 256, 3)).copy()
    params = f"range={range_name}:colorspace={matrix}:color_trc={matrix}:color_primaries={matrix}"
    subprocess.run([
        "ffmpeg", "-v", "error", "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "256x96",
        "-framerate", "25", "-i", "pipe:0", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
        "-t", "0.16", "-vf", f"scale=in_range=full:out_range={range_name}:out_color_matrix={matrix},setparams={params}",
        "-c:v", "libx264", "-crf", "0", "-pix_fmt", "yuv420p", "-colorspace", matrix,
        "-color_range", "pc" if range_name == "full" else "tv", "-color_trc", matrix,
        "-color_primaries", matrix, "-c:a", "pcm_s16le", "-n", str(path),
    ], input=rgb.tobytes() * 4, check=True, capture_output=True)


@pytest.mark.parametrize("matrix", ["bt709", "smpte170m"])
@pytest.mark.parametrize("range_name", ["limited", "full"])
@pytest.mark.parametrize("codec", ["h264", "hevc", "av1"])
def test_selected_frame_rgb_stages_and_export_keep_real_colors(tmp_path, matrix, range_name, codec):
    source = tmp_path / "source.mkv"
    source_clip(source, matrix, range_name)
    original = probe(source)
    expected = read_rgb(source, matrix, range_name)
    wrong = read_rgb(source, "smpte170m" if matrix == "bt709" else "bt709", range_name)
    assert np.mean(np.abs(expected.astype(int) - wrong.astype(int))) > 5
    selected = tmp_path / "selected.mkv"
    assert sample(source, selected, 0, Fraction(1, 25)) == 1
    color = SDRColor.read(source)
    assert SDRColor.read(selected) == color
    with av.open(selected) as container:
        picture = next(container.decode(video=0))
        pixels = color.rgb(picture)
    assert np.mean(np.abs(pixels.astype(int) - expected.astype(int))) < 2
    # Two real lossless NUT stages mirror independent SR/FG processes. Exact
    # RGB roundtrip proves the profile describes final YUV, not working RGB.
    current = selected
    for index in range(2):
        stage = tmp_path / f"stage-{index}.nut"
        profile = SDRColor.read(current)
        with av.open(current) as container, encoded_video(
            stage, 256, 96, Fraction(25), Fraction(1, 1000), encoding_options("ffv1", 23), sdr_color=profile,
        ) as (output, stream):
            for decoded in container.decode(video=0):
                frame = av.VideoFrame.from_ndarray(profile.rgb(decoded), format="rgb24")
                frame.pts, frame.time_base = 0, Fraction(1, 1000)
                for packet in stream.encode(frame):
                    output.mux(packet)
        assert SDRColor.read(stage) == color
        with av.open(stage) as container:
            np.testing.assert_array_equal(color.rgb(next(container.decode(video=0))), pixels)
        current = stage
    options = {
        "h264": ["-c:v", "libx264", "-crf", "0"],
        "hevc": ["-c:v", "libx265", "-x265-params", "lossless=1:pools=2:frame-threads=1:log-level=error"],
        "av1": ["-c:v", "libsvtav1", "-crf", "0", "-preset", "12", "-svtav1-params", "lp=2"],
    }[codec] + ["-pix_fmt", "yuv420p"]
    export = tmp_path / "export.mkv"
    with encoded_video(export, 256, 96, Fraction(25), Fraction(1, 1000), options, sdr_color=SDRColor.read(current)) as (output, stream):
        frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
        frame.pts, frame.time_base = 0, Fraction(1, 1000)
        for packet in stream.encode(frame):
            output.mux(packet)
    validate_sdr(original, probe(export))
    actual = read_rgb(export, matrix, range_name)
    assert np.mean(np.abs(actual.astype(int) - expected.astype(int))) < 3
    metadata = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_format", "-of", "json", str(export)]))
    assert PROFILE_TAG not in {k.lower() for k in metadata["format"].get("tags", {})}


def test_conventional_resize_and_validation_preserve_known_color(tmp_path):
    source, output = tmp_path / "source.mkv", tmp_path / "output.mkv"
    source_clip(source, "bt709", "full")
    original = probe(source)
    recipe = Recipe(scale=1, preview_seconds=0, quality=16).model_dump()
    subprocess.run(ffmpeg_command(source, output, recipe, original), capture_output=True, check=True)
    validate_output(output, original, recipe)
    assert np.mean(np.abs(read_rgb(output, "bt709", "full").astype(int)
                          - read_rgb(source, "bt709", "full").astype(int))) < 3
    for field in ("color_space", "color_transfer", "color_primaries", "color_range"):
        with pytest.raises(ValueError, match="SDR color"):
            validate_sdr(original, probe(output) | {field: "unknown"})


def test_missing_or_unsupported_color_and_malformed_profiles_fail_honestly(tmp_path):
    assert SDRColor.from_info({}) == SDRColor()
    assert "bt709" not in str(SDRColor().options())
    validate_sdr({}, {})
    for values in ({"colorspace": 9}, {"color_trc": 16}, {"color_range": True}, {"color_primaries": "1"}):
        with pytest.raises(ValueError, match="unsupported"):
            SDRColor(**values)
    source = tmp_path / "source.mkv"
    source_clip(source, "bt709", "limited")
    bad = tmp_path / "bad.nut"
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(source), "-an", "-c:v", "ffv1", "-pix_fmt", "bgr0",
                    "-metadata", PROFILE_TAG + '={"colorspace":1}', "-n", str(bad)], check=True)
    with pytest.raises(ValueError, match="Invalid intermediate"):
        SDRColor.read(bad)


def test_resize_rgb_intermediate_and_cpu_cadence_keep_color_and_clock(tmp_path):
    source = tmp_path / "source.mkv"
    source_clip(source, "bt709", "full")
    original, color = probe(source), SDRColor.read(source)
    recipe = Recipe(scale=1, preview_seconds=0, quality=16).model_dump()
    stage, cadenced, output = (tmp_path / name for name in ("resized.nut", "cadenced.nut", "output.mkv"))
    subprocess.run(ffmpeg_command(source, stage, recipe | {"codec": "ffv1"}, original, video_only=True),
                   check=True, capture_output=True)
    assert SDRColor.read(stage) == color
    # Real CPU cadence export tests clocks/profile handling only, not DLSSG.
    assert cadence(stage, cadenced, Fraction(50), Fraction(4, 25), "ffv1", 23) == 8
    assert SDRColor.read(cadenced) == color
    with av.open(cadenced) as container:
        timestamps = [Fraction(f.pts) * f.time_base for f in container.decode(video=0)]
    assert timestamps == [Fraction(i, 50) for i in range(8)]
    subprocess.run(ffmpeg_command(cadenced, output, recipe, original, video_only=True), check=True, capture_output=True)
    validate_sdr(original, probe(output))
    assert np.mean(np.abs(read_rgb(output, "bt709", "full").astype(int)
                          - read_rgb(source, "bt709", "full").astype(int))) < 3


def test_dynamic_color_changes_are_rejected_before_conversion():
    color = SDRColor(1, 1, 1, 1)
    frame = av.VideoFrame(64, 48, "yuv420p")
    frame.colorspace, frame.color_range, frame.color_trc, frame.color_primaries = 1, 1, 1, 1
    for field, value in (("colorspace", 6), ("color_range", 2), ("color_trc", 6), ("color_primaries", 6)):
        before = getattr(frame, field)
        setattr(frame, field, value)
        with pytest.raises(ValueError, match="changed during decoding"):
            color.rgb(frame)
        setattr(frame, field, before)
