import json
import subprocess
from fractions import Fraction

import av
import pytest

from popcorn_sr.video_pipe import encoded_video


def test_frame_pipe_preserves_variable_timing_and_reports_encoder_failure(tmp_path):
    result = tmp_path / "variable.mkv"
    timestamps = [0, 40, 120, 200]

    def write_frames(output, stream):
        for pts in timestamps:
            frame = av.VideoFrame(64, 48, "rgb24")
            frame.planes[0].update(bytes([pts]) * frame.planes[0].buffer_size)
            frame.pts, frame.time_base = pts, Fraction(1, 1000)
            for packet in stream.encode(frame):
                output.mux(packet)

    with encoded_video(
        result, 64, 48, Fraction(25), Fraction(1, 1000),
        ["-c:v", "libx264", "-bf", "0", "-pix_fmt", "yuv420p"],
    ) as (output, stream):
        write_frames(output, stream)
    frames = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames",
        "-show_entries", "frame=best_effort_timestamp_time", "-of", "json", str(result),
    ]))["frames"]
    assert [float(f["best_effort_timestamp_time"]) for f in frames] == pytest.approx(
        [t / 1000 for t in timestamps], abs=0.001
    )
    assert set(tmp_path.iterdir()) == {result}
    metadata = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-of", "json", str(result),
    ]))["streams"][0]
    assert Fraction(metadata["avg_frame_rate"]) == 25

    with pytest.raises(RuntimeError, match="FFmpeg video encoding failed"):
        with encoded_video(
            tmp_path / "bad.mkv", 64, 48, Fraction(25), Fraction(1, 1000),
            ["-c:v", "missing_encoder"],
        ) as (output, stream):
            write_frames(output, stream)
