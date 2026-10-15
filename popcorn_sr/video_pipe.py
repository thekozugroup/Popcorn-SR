"""Send timestamped frames to system FFmpeg without PyAV's optional GPU codecs."""

import os
import subprocess
import threading
from contextlib import contextmanager
from fractions import Fraction


def nvidia_options(codec, quality):
    return [
        "-c:v", f"{codec}_nvenc", "-preset", "p6", "-rc", "vbr",
        "-cq", str(quality), "-b:v", "0", "-bf", "0", "-pix_fmt", "yuv420p",
    ]


def encoding_options(codec, quality):
    if codec == "ffv1":
        # Internal RGB intermediate; NUT retains sub-millisecond timestamps.
        return ["-c:v", "ffv1", "-level", "3", "-coder", "1", "-context", "1", "-pix_fmt", "bgr0"]
    return nvidia_options(codec, quality)


@contextmanager
def encoded_video(path, width, height, rate, time_base, options, *, end_time=None, final_frame_time=None,
                  input_pix_fmt="rgb24", color_metadata=None, sdr_color=None):
    """NUT carries original PTS through a bounded OS pipe, including variable timing."""
    import av

    if input_pix_fmt not in {"rgb24", "gbrp10le"}:
        raise ValueError("Frame pipe requires verified RGB8 or planar RGB10; packed HDR is unsupported.")
    if set(color_metadata or {}) - {"color_range", "colorspace", "color_trc", "color_primaries"}:
        raise ValueError("Unsupported video color metadata field.")
    if sdr_color is not None:
        if color_metadata is not None or input_pix_fmt != "rgb24":
            raise ValueError("SDR and HDR frame-pipe color profiles cannot be combined.")
        intermediate = "-c:v" in options and options[options.index("-c:v") + 1] == "ffv1"
        options = [*options, *sdr_color.options(intermediate=intermediate)]
        color_metadata = {"colorspace": 0, "color_range": 2, "color_trc": sdr_color.color_trc,
                          "color_primaries": sdr_color.color_primaries}
    inherited = {}
    if os.name == "posix" and (active_fd := os.environ.get("POPCORN_ACTIVE_JOB_FD")):
        # Keep job ownership alive even if the AI process exits before FFmpeg.
        fd = int(active_fd)
        os.fstat(fd)
        inherited["pass_fds"] = (fd,)
    duration_options = []
    if end_time is not None:
        end = Fraction(end_time)
        if end <= 0:
            raise ValueError("Video end time must be positive.")
        # Clip the final encoded packet when the duration is not a whole tick.
        # Matroska uses millisecond ticks. A rounded zero duration means
        # "unknown" to its muxer and expands to a whole nominal frame.
        expression = f"max(ceil(0.001/TB),min(DURATION,max(0,({end.numerator}/{end.denominator})/TB-PTS)))"
        if final_frame_time is not None:
            last = Fraction(final_frame_time)
            if not 0 <= last < end:
                raise ValueError("Final picture must precede the video end time.")
            # An irregular final interval can be longer than nominal FPS. Its
            # measured final PTS identifies the final packet without guessing
            # from the duration supplied by a re-encoder.
            final_tick = f"round(({last.numerator}/{last.denominator})/TB)"
            remaining = f"max(ceil(0.001/TB),({end.numerator}/{end.denominator})/TB-PTS)"
            expression = f"if(gte(PTS,{final_tick}),{remaining},{expression})"
        duration_options = ["-bsf:v", f"setts=duration='{expression}'"]
    elif final_frame_time is not None:
        raise ValueError("Final picture timing requires a measured video end time.")
    process = subprocess.Popen(
        [
            "ffmpeg", "-v", "error", "-nostdin", "-filter_threads", "1", "-threads", "2",
            "-f", "nut", "-i", "pipe:0", "-map", "0:v:0", "-threads", "2",
            *options, *duration_options, "-fps_mode", "passthrough",
            "-enc_time_base", "demux", "-n", str(path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        **inherited,
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
                video.pix_fmt = input_pix_fmt
                video.time_base = time_base
                video.codec_context.time_base = time_base
                for field, value in (color_metadata or {}).items():
                    setattr(video.codec_context, field, value)
                for_frame = (output, video)
                yield for_frame
                for packet in video.encode(None):
                    output.mux(packet)
        except (BrokenPipeError, av.error.PyAVCallbackError) as exc:
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
