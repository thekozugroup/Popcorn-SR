"""Experimental native NGX CUDA Super Resolution for timestamped SDR video."""

import argparse
import ctypes
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path

from .dlss import MODES, PRESETS
from .media import probe
from .video_pipe import encoded_video, encoding_options


class MotionEstimator:
    """Estimate current-to-previous pixel motion; reset history at cuts/time gaps."""

    def __init__(self, quality="high"):
        import cv2

        if quality not in {"low", "medium", "high"}:
            raise ValueError("Unknown temporal quality.")
        cv2.setNumThreads(2)
        self.quality = quality
        self.previous = self.histogram = self.time = None

    def estimate(self, rgb, timestamp, period):
        import cv2
        import numpy as np

        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        hist = cv2.calcHist([gray], [0], None, [32], [0, 256])
        hist /= max(float(hist.sum()), 1)
        reset = self.previous is None
        if not reset:
            if timestamp <= self.time:
                raise ValueError("Video timestamps must increase; refusing to change timing.")
            reset = timestamp - self.time > max(Fraction(1, 2), period * 5)
            reset |= self.previous.shape != gray.shape
            reset |= cv2.compareHist(self.histogram, hist, cv2.HISTCMP_BHATTACHARYYA) > 0.55
            if not reset:
                reset |= np.mean(np.abs(gray.astype(np.float32) - self.previous)) > 90
        if reset:
            motion = np.zeros((*gray.shape, 2), np.float32)
        else:
            factor = {"low": 0.25, "medium": 0.5, "high": 1.0}[self.quality]
            w, h = max(16, round(gray.shape[1] * factor)), max(16, round(gray.shape[0] * factor))
            current = cv2.resize(gray, (w, h), interpolation=cv2.INTER_AREA)
            previous = cv2.resize(self.previous, (w, h), interpolation=cv2.INTER_AREA)
            # NGX expects backward flow, expressed in input-resolution pixel units.
            motion = cv2.calcOpticalFlowFarneback(
                current, previous, None, 0.5, 5 if self.quality == "high" else 3,
                21, 5 if self.quality == "high" else 3, 7, 1.5, cv2.OPTFLOW_FARNEBACK_GAUSSIAN,
            )
            motion = cv2.resize(motion, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)
            motion[:, :, 0] *= gray.shape[1] / w
            motion[:, :, 1] *= gray.shape[0] / h
            if not np.isfinite(motion).all():
                raise ValueError("Motion estimation produced invalid values.")
        self.previous, self.histogram, self.time = gray, hist, timestamp
        return np.ascontiguousarray(motion, dtype=np.float32), bool(reset)


class NativeDLSS:
    """Own one NGX session. Never substitute conventional pixels after an error."""

    def __init__(self, library, runtime, scratch, width, height, out_width, out_height, mode, preset):
        import numpy as np

        self.handle = None
        self.library = ctypes.CDLL(str(Path(library).resolve()))
        self.library.popcorn_dlss_abi_version.restype = ctypes.c_uint
        if self.library.popcorn_dlss_abi_version() != 1:
            raise RuntimeError("Unsupported native DLSS bridge version. Rebuild it with this worker source.")
        self.library.popcorn_dlss_error.restype = ctypes.c_char_p
        floats = np.ctypeslib.ndpointer(dtype=np.float32, flags="C_CONTIGUOUS")
        self.library.popcorn_dlss_create.argtypes = [
            ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_int,
            ctypes.c_uint, ctypes.c_char_p, ctypes.c_char_p,
        ]
        self.library.popcorn_dlss_create.restype = ctypes.c_void_p
        self.library.popcorn_dlss_process.argtypes = [ctypes.c_void_p, floats, floats, floats, ctypes.c_int]
        self.library.popcorn_dlss_process.restype = ctypes.c_int
        self.library.popcorn_dlss_destroy.argtypes = [ctypes.c_void_p]
        self.library.popcorn_dlss_destroy.restype = None
        self.width, self.height = width, height
        self.input = np.ones((height, width, 4), np.float32)
        self.output = np.empty((out_height, out_width, 4), np.float32)
        self.handle = self.library.popcorn_dlss_create(
            width, height, out_width, out_height, MODES[mode][0], PRESETS[preset],
            os.fsencode(Path(runtime).resolve()), os.fsencode(Path(scratch).resolve()),
        )
        if not self.handle:
            raise RuntimeError(self.error())

    def error(self):
        return (self.library.popcorn_dlss_error() or b"Unknown DLSS failure").decode(errors="replace")

    def process(self, rgb, motion, reset):
        import numpy as np

        if rgb.shape != (self.height, self.width, 3) or rgb.dtype != np.uint8:
            raise ValueError("DLSS input dimensions/format changed during this video.")
        if motion.shape != (self.height, self.width, 2) or motion.dtype != np.float32:
            raise ValueError("Invalid DLSS motion buffer.")
        if not self.handle:
            raise RuntimeError("DLSS session is closed.")
        self.input[:, :, :3] = rgb / np.float32(255)
        self.output.fill(np.nan)
        if self.library.popcorn_dlss_process(self.handle, self.input, motion, self.output, int(reset)):
            raise RuntimeError(self.error())
        if not np.isfinite(self.output).all():
            raise RuntimeError("DLSS did not produce a complete finite frame.")
        return np.ascontiguousarray(np.rint(np.clip(self.output[:, :, :3], 0, 1) * 255), dtype=np.uint8)

    def close(self):
        if self.handle:
            self.library.popcorn_dlss_destroy(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@contextmanager
def driver_scratch(output):
    keys = ("HOME", "TMPDIR", "XDG_CACHE_HOME", "CUDA_CACHE_PATH")
    previous = {key: os.environ.get(key) for key in keys}
    try:
        with tempfile.TemporaryDirectory(prefix="ngx-", dir=Path(output).resolve().parent) as scratch:
            os.chmod(scratch, 0o700)
            os.environ.update(dict.fromkeys(keys, scratch))
            yield scratch
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def render(args):
    import av

    info = probe(Path(args.input))
    if info["hdr"] or info["bit_depth"] != 8:
        raise ValueError("Native DLSS video currently accepts 8-bit SDR only.")
    if not Path(args.runtime).is_dir():
        raise ValueError("DLSS SDK runtime folder is missing.")
    # The entire NGX/driver cache lifetime belongs to this job, on its scratch drive.
    keys = ("HOME", "TMPDIR", "XDG_CACHE_HOME", "CUDA_CACHE_PATH")
    previous_env = {key: os.environ.get(key) for key in keys}
    try:
        with tempfile.TemporaryDirectory(prefix="ngx-", dir=Path(args.output).resolve().parent) as scratch:
            os.chmod(scratch, 0o700)
            os.environ.update(dict.fromkeys(keys, scratch))
            with NativeDLSS(
                args.library, args.runtime, scratch, info["width"], info["height"],
                args.width, args.height, args.mode, args.preset,
            ) as dlss, av.open(args.input, options={"protocol_whitelist": "file,pipe"}) as source:
                video = next(s for s in source.streams.video if not (s.disposition.value & 1024))
                if not video.average_rate or not video.time_base:
                    raise ValueError("Frame rate/time base unavailable; refusing to guess timing.")
                motion = MotionEstimator(args.temporal_quality)
                first, count, resets = None, 0, 0
                with encoded_video(
                    args.output, args.width, args.height, video.average_rate, video.time_base,
                    encoding_options(args.codec, args.quality),
                ) as (output, encoded):
                    for frame in source.decode(video):
                        if frame.pts is None or frame.time_base is None:
                            raise ValueError("Missing frame timestamps; refusing to change timing.")
                        timestamp = Fraction(frame.pts) * frame.time_base
                        first = timestamp if first is None else first
                        rgb = frame.to_ndarray(format="rgb24")
                        flow, reset = motion.estimate(rgb, timestamp, 1 / video.average_rate)
                        result = av.VideoFrame.from_ndarray(dlss.process(rgb, flow, reset), format="rgb24")
                        result.pts = frame.pts - int(first / frame.time_base)
                        result.time_base = Fraction(frame.time_base)
                        for packet in encoded.encode(result):
                            output.mux(packet)
                        count += 1
                        resets += reset
                        print(f"out_time_us={int((timestamp - first) * 1_000_000)}", flush=True)
                if not count:
                    raise ValueError("Video contained no decodable frames.")
                print(f"dlss_frames={count}\ndlss_history_resets={resets}", flush=True)
    finally:
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def pixel_check(args):
    """Three decoded frames, including actual temporal evaluation and readback."""
    import av

    from .media import dimensions

    info = probe(Path(args.input))
    if info["hdr"] or info["bit_depth"] != 8:
        raise ValueError("DLSS settings checks require 8-bit SDR.")
    with av.open(args.input) as source:
        video = next(s for s in source.streams.video if not (s.disposition.value & 1024))
        frames = []
        for frame in source.decode(video):
            frames.append((frame.to_ndarray(format="rgb24"), Fraction(frame.pts) * frame.time_base))
            if len(frames) == 3:
                break
        if len(frames) != 3 or not video.average_rate:
            raise ValueError("Settings check requires three timestamped frames.")
        period = 1 / video.average_rate
    with driver_scratch(args.output) as scratch:
        w, h = dimensions(info, {"engine": "dlss-sr", "scale": 2, "dlss_mode": args.mode})
        with NativeDLSS(args.library, args.runtime, scratch, info["width"], info["height"], w, h, args.mode, args.preset) as dlss:
            estimator = MotionEstimator(args.temporal_quality)
            for rgb, timestamp in frames:
                flow, reset = estimator.estimate(rgb, timestamp, period)
                dlss.process(rgb, flow, reset)


def verify_settings(args):
    """Check each configuration in a fresh NGX process, with bounded timeouts."""
    settings, temporal_qualities = [], []
    report = Path(args.verify_settings)

    def save():
        pending = report.with_suffix(".pending")
        pending.write_text(json.dumps({"settings": settings, "temporal_qualities": temporal_qualities}))
        pending.replace(report)

    def check(mode, preset, temporal):
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m", "popcorn_sr.dlss_sr", "--input", args.input,
                    "--output", str(Path(scratch) / "check.mkv"), "--width", str(args.width), "--height", str(args.height),
                    "--library", args.library, "--runtime", args.runtime,
                    "--mode", mode, "--preset", preset, "--temporal-quality", temporal, "--pixel-check",
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20,
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            return False

    with driver_scratch(args.output) as scratch:
        for mode in MODES:
            for preset in PRESETS:
                if check(mode, preset, "high"):
                    settings.append([mode, preset])
                save()
        for quality in ("low", "medium", "high"):
            if check(args.mode, args.preset, quality):
                temporal_qualities.append(quality)
            save()


def main():
    parser = argparse.ArgumentParser(description="Native CUDA DLSS SDR video adapter (experimental)")
    for key in ("input", "output", "library", "runtime"):
        parser.add_argument(f"--{key}", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--mode", choices=MODES, default="performance")
    parser.add_argument("--preset", choices=PRESETS, default="default")
    parser.add_argument("--temporal-quality", choices=["low", "medium", "high"], default="high")
    parser.add_argument("--codec", choices=["h264", "hevc", "av1", "ffv1"], default="h264")
    parser.add_argument("--quality", type=int, choices=range(16, 33), default=23)
    parser.add_argument("--verify-settings", help="Write actual mode/preset pixel-check results instead of a video")
    parser.add_argument("--pixel-check", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.verify_settings:
        verify_settings(args)
    elif args.pixel_check:
        pixel_check(args)
    else:
        render(args)


if __name__ == "__main__":
    main()
