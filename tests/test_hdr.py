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


def frames(path, options, *, width=1024, height=64):
    values = words(width, height)
    with encoded_video(path, width, height, Fraction(25), Fraction(1, 1000), options,
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
def test_real_ten_bit_exports_preserve_hdr_signaling_and_variable_timing(tmp_path, codec):
    path = tmp_path / (codec + ".mkv")
    # CPU diagnostic fixtures only. Actual TrueHDR always requires NVENC.
    options = ["-c:v", "libx265", "-preset", "ultrafast", "-x265-params", "lossless=1:pools=2:frame-threads=1:log-level=error"] if codec == "hevc" else [
        "-c:v", "libsvtav1", "-preset", "12", "-crf", "18", "-svtav1-params", "lp=2",
    ]
    options += ["-pix_fmt", "yuv420p10le", *HDR10_SIGNALING]
    frames(path, options)
    info = probe(path)
    validate_hdr(info)
    assert info["codec"] == codec
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
