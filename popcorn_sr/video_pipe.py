"""Send timestamped frames to system FFmpeg without PyAV's optional GPU codecs."""

import subprocess
import threading
from contextlib import contextmanager


def nvidia_options(codec, quality):
    return [
        "-c:v", f"{codec}_nvenc", "-preset", "p6", "-rc", "vbr",
        "-cq", str(quality), "-b:v", "0", "-pix_fmt", "yuv420p",
    ]


@contextmanager
def encoded_video(path, width, height, rate, time_base, options):
    """NUT carries original PTS through a bounded OS pipe, including variable timing."""
    import av

    process = subprocess.Popen(
        [
            "ffmpeg", "-v", "error", "-nostdin", "-f", "nut", "-i", "pipe:0",
            "-map", "0:v:0", *options, "-fps_mode", "passthrough",
            "-enc_time_base", "-1", "-n", str(path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    tail = bytearray()

    def errors():
        while chunk := process.stderr.read(8192):
            tail.extend(chunk)
            if len(tail) > 8192:
                del tail[:-8192]

    reader = threading.Thread(target=errors, daemon=True)
    reader.start()
    broken = None
    try:
        try:
            with av.open(process.stdin, mode="w", format="nut") as output:
                video = output.add_stream("rawvideo", rate=rate)
                video.width, video.height = width, height
                video.pix_fmt = "rgb24"
                video.time_base = time_base
                video.codec_context.time_base = time_base
                for_frame = (output, video)
                yield for_frame
                for packet in video.encode(None):
                    output.mux(packet)
        except BrokenPipeError as exc:
            broken = exc
        finally:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
        try:
            code = process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Video encoder did not finish after receiving its frames.") from None
        reader.join(timeout=5)
        if code or broken:
            raise RuntimeError("FFmpeg video encoding failed: " + tail.decode(errors="replace")[-1500:]) from broken
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        reader.join(timeout=5)
        process.stderr.close()
