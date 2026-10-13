"""Experimental native Vulkan DLSSG for timestamped 8-bit SDR video."""

import argparse
import ctypes
import math
import os
import tempfile
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path

from .dlss_sr import MotionEstimator
from .media import probe
from .sdr import SDRColor
from .video_pipe import encoded_video, encoding_options


def intermediate_times(previous, current, factor):
    """Place genuine SDK outputs strictly between their adjacent source frames."""
    if not 2 <= factor <= 8:
        raise ValueError("Native frame multiplier must be between 2 and 8.")
    previous, current = Fraction(previous), Fraction(current)
    if current <= previous:
        raise ValueError("Video timestamps must increase; refusing to change timing.")
    return tuple(previous + (current - previous) * index / factor for index in range(1, factor))


def output_time_base(source_time_base, source_rate, factor):
    """Represent source ticks, cinema periods and intermediate positions exactly."""
    source_time_base, source_rate = Fraction(source_time_base), Fraction(source_rate)
    if source_time_base <= 0 or source_rate <= 0 or not 2 <= factor <= 8:
        raise ValueError("Positive timing and a supported frame multiplier are required.")
    denominator = math.lcm(source_time_base.denominator, source_rate.numerator) * factor
    if denominator > 2_147_483_647:
        raise ValueError("Video timing exceeds the encoder's exact clock range.")
    return Fraction(1, denominator)


@contextmanager
def graphics_scratch(output):
    keys = (
        "HOME", "TMPDIR", "XDG_CACHE_HOME", "CUDA_CACHE_PATH",
        "__GL_SHADER_DISK_CACHE_PATH", "MESA_SHADER_CACHE_DIR",
    )
    previous = {key: os.environ.get(key) for key in keys}
    try:
        with tempfile.TemporaryDirectory(prefix="dlssg-", dir=Path(output).resolve().parent) as scratch:
            os.chmod(scratch, 0o700)
            os.environ.update(dict.fromkeys(keys, scratch))
            yield scratch
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class NativeDLSSG:
    """One native session per adapter process; each result comes from NVIDIA."""

    def __init__(self, library, runtime, scratch, width, height, factor=2):
        if not 2 <= factor <= 8:
            raise ValueError("Native frame multiplier must be between 2 and 8.")
        self.width, self.height, self.factor = width, height, factor
        self.handle = None
        self.library = ctypes.CDLL(str(Path(library).resolve()))
        lib = self.library
        lib.popcorn_dlssg_abi_version.restype = ctypes.c_int
        if lib.popcorn_dlssg_abi_version() != 1:
            raise ValueError("Incompatible native DLSSG bridge ABI.")
        lib.popcorn_dlssg_error.restype = ctypes.c_char_p
        lib.popcorn_dlssg_create.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p]
        lib.popcorn_dlssg_create.restype = ctypes.c_void_p
        lib.popcorn_dlssg_max_frames.argtypes = [ctypes.c_void_p]
        lib.popcorn_dlssg_max_frames.restype = ctypes.c_uint
        lib.popcorn_dlssg_process.argtypes = [ctypes.c_void_p] * 4 + [ctypes.c_int, ctypes.c_uint, ctypes.c_void_p]
        lib.popcorn_dlssg_process.restype = ctypes.c_int
        lib.popcorn_dlssg_destroy.argtypes = [ctypes.c_void_p]
        self.handle = lib.popcorn_dlssg_create(width, height, factor - 1, os.fsencode(runtime), os.fsencode(scratch))
        if not self.handle:
            raise RuntimeError(self.error())
        self.maximum_factor = lib.popcorn_dlssg_max_frames(self.handle) + 1

    def error(self):
        return (self.library.popcorn_dlssg_error() or b"Native DLSSG failed.").decode(errors="replace")

    def process(self, rgb, motion, reset):
        import numpy as np

        if self.handle is None:
            raise ValueError("Native DLSSG session is closed.")
        if rgb.shape != (self.height, self.width, 3) or rgb.dtype != np.uint8:
            raise ValueError("DLSSG requires fixed-size uint8 RGB frames.")
        if motion.shape != (self.height, self.width, 2) or not np.isfinite(motion).all():
            raise ValueError("Invalid DLSSG motion vectors.")
        rgba = np.empty((self.height, self.width, 4), np.uint8)
        rgba[:, :, :3], rgba[:, :, 3] = rgb, 255
        flow = np.ascontiguousarray(motion, dtype=np.float32)
        for index in range(1, self.factor):
            output = np.empty_like(rgba)
            disabled = ctypes.c_ubyte(255)
            result = self.library.popcorn_dlssg_process(
                self.handle, rgba.ctypes.data, flow.ctypes.data, output.ctypes.data,
                int(reset), index, ctypes.byref(disabled),
            )
            if result:
                raise RuntimeError(self.error())
            yield np.ascontiguousarray(output[:, :, :3]), bool(disabled.value)

    def close(self):
        if self.handle:
            self.library.popcorn_dlssg_destroy(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def render(args):
    import av
    import numpy as np

    info = probe(Path(args.input))
    if info["hdr"] or info["bit_depth"] != 8:
        raise ValueError("Native DLSSG video currently accepts 8-bit SDR only.")
    if info["width"] % 2 or info["height"] % 2:
        raise ValueError("NVENC video output requires even dimensions.")
    if not Path(args.runtime).is_dir():
        raise ValueError("DLSSG SDK runtime folder is missing.")
    if not 0 <= args.quality <= 51:
        raise ValueError("Encoder quality must be between 0 and 51.")
    with graphics_scratch(args.output) as scratch, av.open(args.input, options={"protocol_whitelist": "file,pipe"}) as source:
        color = SDRColor.read(args.input)
        video = next(stream for stream in source.streams.video if not (stream.disposition.value & 1024))
        if not video.average_rate or not video.time_base:
            raise ValueError("Frame rate/time base unavailable; refusing to guess timing.")
        # Anamorphic geometry needs a separate preservation check before enabling.
        if video.sample_aspect_ratio and video.sample_aspect_ratio != 1:
            raise ValueError("Native DLSSG anamorphic video preservation is not verified yet.")
        nominal = Fraction(args.source_rate) if args.source_rate else video.average_rate
        if nominal <= 0:
            raise ValueError("Source frame rate must be positive.")
        rate = nominal * args.factor
        time_base = output_time_base(video.time_base, nominal, args.factor)
        limit = 3840 if args.codec == "ffv1" else 480
        if rate > limit:
            raise ValueError(f"Native output exceeds {limit} frames per second.")
        estimator = MotionEstimator(args.temporal_quality)
        count, output_count, disabled_count, resets = 0, 0, 0, 0
        first, previous, last_rgb, last_duration = None, None, None, None
        with NativeDLSSG(args.library, args.runtime, scratch, info["width"], info["height"], args.factor) as engine:
            with encoded_video(args.output, info["width"], info["height"], rate, time_base, encoding_options(args.codec, args.quality),
                               sdr_color=color) as (output, encoded):
                def write(rgb, timestamp):
                    nonlocal output_count
                    frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
                    ticks = (timestamp - first) / time_base
                    if ticks.denominator != 1:
                        raise ValueError("Output time base cannot represent frame timing exactly.")
                    frame.pts, frame.time_base = ticks.numerator, time_base
                    for packet in encoded.encode(frame):
                        output.mux(packet)
                    output_count += 1

                for frame in source.decode(video):
                    if frame.pts is None or frame.time_base is None:
                        raise ValueError("Missing frame timestamps; refusing to change timing.")
                    timestamp = Fraction(frame.pts) * frame.time_base
                    rgb = color.rgb(frame)
                    motion, reset = estimator.estimate(rgb, timestamp, 1 / nominal)
                    resets += reset
                    first = timestamp if first is None else first
                    if previous is None:
                        # Prime SDK history; reset outputs are source copies.
                        for _priming_frame in engine.process(rgb, motion, True):
                            pass
                    else:
                        times = intermediate_times(previous, timestamp, args.factor)
                        for generated_time, (generated, disabled) in zip(times, engine.process(rgb, motion, reset), strict=True):
                            write(generated, generated_time)
                            disabled_count += disabled
                    write(rgb, timestamp)
                    duration = getattr(frame, "duration", 0)
                    last_duration = Fraction(duration) * frame.time_base if duration and duration > 0 else 1 / nominal
                    previous, last_rgb = timestamp, rgb
                    count += 1
                    print(f"out_time_us={int((timestamp - first) * 1_000_000)}", flush=True)
                if not count:
                    raise ValueError("Video contained no decodable frames.")
                # Hold the last source frame for its final interval. The SDK still
                # evaluates it; no extrapolated scene content or substitute filter.
                times = intermediate_times(previous, previous + last_duration, args.factor)
                motion = np.zeros((info["height"], info["width"], 2), np.float32)
                for timestamp, (generated, disabled) in zip(times, engine.process(last_rgb, motion, False), strict=True):
                    write(generated, timestamp)
                    disabled_count += disabled
            print(
                f"dlssg_source_frames={count}\ndlssg_output_frames={output_count}\n"
                f"dlssg_multiplier={args.factor}\ndlssg_native_maximum_factor={engine.maximum_factor}\n"
                f"dlssg_disabled_interpolations={disabled_count}\ndlssg_history_resets={resets}",
                flush=True,
            )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--library", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--factor", type=int, choices=range(2, 9), default=2)
    parser.add_argument("--source-rate", help="Nominal rational rate carried between lossless cascade passes")
    parser.add_argument("--temporal-quality", choices=("high", "medium", "low"), default="high")
    parser.add_argument("--codec", choices=("h264", "hevc", "av1", "ffv1"), default="h264")
    parser.add_argument("--quality", type=int, default=20)
    parser.add_argument("--inspect-native", action="store_true", help="Query native limits only; does not verify rendered video.")
    args = parser.parse_args()
    if args.inspect_native:
        import json

        info = probe(Path(args.input))
        with graphics_scratch(args.output) as scratch, NativeDLSSG(
            args.library, args.runtime, scratch, info["width"], info["height"], 2,
        ) as engine:
            print("dlssg_native_info=" + json.dumps({"maximum_factor": min(engine.maximum_factor, 8), "render_verified": False}), flush=True)
    else:
        render(args)


if __name__ == "__main__":
    main()
