"""Native DLSSG frame cadence and lossless cascade orchestration.

Only NVIDIA creates intermediate pixels. The cadence pass chooses an existing
source/SDK frame nearest each output tick; it never blends or invents pixels.
"""

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

from .media import probe
from .video_pipe import encoded_video, encoding_options

FPS = {
    "23.976": Fraction(24000, 1001), "25": Fraction(25),
    "29.97": Fraction(30000, 1001), "30": Fraction(30), "50": Fraction(50),
    "59.94": Fraction(60000, 1001), "60": Fraction(60), "90": Fraction(90),
    "119.88": Fraction(120000, 1001), "120": Fraction(120), "144": Fraction(144),
    "165": Fraction(165), "180": Fraction(180), "240": Fraction(240),
    "360": Fraction(360), "480": Fraction(480),
}


def plan_factors(source_rate, target_rate, maximum, mode="auto"):
    source_rate, target_rate = Fraction(source_rate), Fraction(target_rate)
    if source_rate <= 0 or target_rate <= source_rate or target_rate > 480:
        raise ValueError("Choose a target above the incoming frame rate, up to 480 fps.")
    if not 2 <= maximum <= 8 or mode not in {"auto", "native", "cascade"}:
        raise ValueError("A supported native limit and frame-generation mode are required.")
    ratio = target_rate / source_rate
    if mode == "native":
        factor = math.ceil(ratio)
        if factor > maximum:
            raise ValueError("Target exceeds the native DLSSG limit. Choose Auto or Cascade.")
        return (factor,)
    factors = []
    while ratio > 1:
        factor = 2 if mode == "cascade" else min(maximum, math.ceil(ratio))
        factors.append(factor)
        ratio /= factor
        if len(factors) > 16:
            raise ValueError("Requested cascade exceeds the bounded pass limit.")
    return tuple(factors)


def nearest_frames(frames, rate, end):
    """Stream a CFR grid with bounded lookahead, maintaining exact rational PTS."""
    rate, end = Fraction(rate), Fraction(end)
    if rate <= 0 or end <= 0:
        raise ValueError("Positive output frame rate and video duration are required.")
    iterator = iter(frames)
    previous = next(iterator, None)
    if previous is None or previous[0] != 0:
        raise ValueError("Cadence input must begin at timestamp zero.")
    current = next(iterator, None)
    index = 0
    while Fraction(index, 1) / rate < end:
        timestamp = Fraction(index, 1) / rate
        while current is not None and current[0] <= timestamp:
            if current[0] <= previous[0]:
                raise ValueError("Cadence input timestamps must increase.")
            previous, current = current, next(iterator, None)
        if current is not None and current[0] <= previous[0]:
            raise ValueError("Cadence input timestamps must increase.")
        selected = previous
        if current is not None and current[0] < end and current[0] - timestamp < timestamp - previous[0]:
            selected = current
        yield timestamp, min(1 / rate, end - timestamp), selected[1]
        index += 1


def source_timeline(path):
    import av

    with av.open(str(path), options={"protocol_whitelist": "file,pipe"}) as source:
        video = next(s for s in source.streams.video if not (s.disposition.value & 1024))
        if not video.average_rate or not video.time_base:
            raise ValueError("Source frame rate/time base unavailable; refusing to guess timing.")
        first, previous, count, duration = None, None, 0, None
        for frame in source.decode(video):
            if frame.pts is None or frame.time_base is None:
                raise ValueError("Source frame timestamp is missing.")
            timestamp = Fraction(frame.pts) * frame.time_base
            if previous is not None and timestamp <= previous:
                raise ValueError("Source timestamps must increase.")
            first = timestamp if first is None else first
            duration = Fraction(frame.duration) * frame.time_base if frame.duration and frame.duration > 0 else 1 / video.average_rate
            previous, count = timestamp, count + 1
        if not count:
            raise ValueError("Source has no decodable frames.")
        return {"rate": video.average_rate, "duration": previous - first + duration, "frames": count,
                "last_frame_time": previous - first, "time_base": Fraction(video.time_base)}


def source_timing(path):
    timing = source_timeline(path)
    return timing["rate"], timing["duration"], timing["frames"]


def adapter_process(command):
    """Keep the parent job lock inherited and propagate bounded progress lines."""
    inherited = {}
    if os.name == "posix" and (active := os.environ.get("POPCORN_ACTIVE_JOB_FD")):
        inherited["pass_fds"] = (int(active),)
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, text=True, **inherited)
    report = None
    try:
        for line in process.stdout:
            if line.startswith("dlssg_native_info="):
                report = json.loads(line.split("=", 1)[1])
            elif line.startswith(("out_time_us=", "dlssg_")):
                print(line.rstrip(), flush=True)
        if process.wait():
            raise RuntimeError("Native DLSSG processing failed; no substitute renderer was used.")
        return report
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()


def cadence(input_path, output_path, rate, end, codec, quality):
    import av

    rate, end = Fraction(rate), Fraction(end)
    with av.open(str(input_path), options={"protocol_whitelist": "file,pipe"}) as source:
        video = source.streams.video[0]
        clock = Fraction(1, math.lcm(rate.numerator, end.denominator))
        if clock.denominator > 2_147_483_647:
            raise ValueError("Source timing exceeds the encoder's exact clock range.")

        def decoded():
            first = None
            for frame in source.decode(video):
                if frame.pts is None or frame.time_base is None:
                    raise ValueError("Generated frame timestamp is missing.")
                timestamp = Fraction(frame.pts) * frame.time_base
                first = timestamp if first is None else first
                yield timestamp - first, frame.to_ndarray(format="rgb24")

        count = 0
        with encoded_video(
            output_path, video.width, video.height, rate, clock,
            encoding_options(codec, quality), end_time=end,
        ) as (output, encoded):
            for timestamp, duration, rgb in nearest_frames(decoded(), rate, end):
                frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
                frame.pts, frame.time_base = int(timestamp / clock), clock
                for packet in encoded.encode(frame):
                    packet.duration = int(duration / packet.time_base)
                    output.mux(packet)
                count += 1
                print(f"out_time_us={int(timestamp * 1_000_000)}", flush=True)
        return count


def render(args):
    info = probe(Path(args.input))
    if info["hdr"] or info["bit_depth"] != 8:
        raise ValueError("Native frame generation currently accepts 8-bit SDR only.")
    rate = FPS[args.fps]
    timing = source_timeline(args.input)
    source_rate, duration, source_count = timing["rate"], timing["duration"], timing["frames"]
    if getattr(args, "source_end_time", None) is not None:
        duration = Fraction(args.source_end_time)
        if duration <= timing["last_frame_time"]:
            raise ValueError("The measured source end must follow its final picture.")
    if rate <= source_rate:
        raise ValueError("Choose a target above the incoming frame rate.")
    with tempfile.TemporaryDirectory(prefix="dlssg-pipeline-", dir=Path(args.output).resolve().parent) as temporary:
        root = Path(temporary)
        base = [sys.executable, "-m", "popcorn_sr.dlssg", "--library", args.library, "--runtime", args.runtime]
        report = adapter_process([*base, "--input", args.input, "--output", str(root / "inspection.nut"), "--inspect-native"])
        if not report or not isinstance(report.get("maximum_factor"), int):
            raise ValueError("Native frame-generation limit unavailable.")
        factors = plan_factors(source_rate, rate, report["maximum_factor"], args.mode)
        previous = Path(args.input).resolve()
        nominal = source_rate
        for index, factor in enumerate(factors):
            current = root / f"pass-{index}.nut"
            adapter_process([
                *base, "--input", str(previous), "--output", str(current),
                "--factor", str(factor), "--source-rate", str(nominal),
                "--codec", "ffv1", "--temporal-quality", args.temporal_quality,
            ])
            nominal *= factor
            if previous.is_relative_to(root):
                previous.unlink()
            previous = current
        count = cadence(previous, args.output, rate, duration, args.codec, args.quality)
        report = {
            "target_fps": str(rate), "mode": args.mode, "native_factors": factors,
            "source_frames": source_count, "output_frames": count, "source_video_duration": str(duration),
            "maximum_factor": report["maximum_factor"],
        }
        if args.report:
            from .scratch import atomic_private_json

            atomic_private_json(Path(args.report), report)
        print("dlssg_pipeline=" + json.dumps(report), flush=True)


def verify_settings(args):
    """Actual short renders of every mode/motion pair, each in a fresh session."""
    import av

    from .scratch import atomic_private_json

    checked = {"settings": [], "maximum_factor": None, "upscalers": ["resize"]}
    with tempfile.TemporaryDirectory(prefix="dlssg-check-", dir=Path(args.output).resolve().parent) as temporary:
        root = Path(temporary)
        clip = root / "source.nut"
        subprocess.run([
            "ffmpeg", "-v", "error", "-nostdin", "-i", args.input, "-map", "0:V:0",
            "-frames:v", "3", "-c:v", "ffv1", "-pix_fmt", "bgr0", "-n", str(clip),
        ], check=True, timeout=30)
        _, end, _ = source_timing(clip)
        for mode in ("native", "auto", "cascade"):
            for quality in ("low", "medium", "high"):
                target = "60" if mode == "native" else "480"
                result, report = root / "result.mkv", root / "result.json"
                command = [
                    sys.executable, "-m", "popcorn_sr.frame_generation", "--input", str(clip),
                    "--output", str(result), "--library", args.library, "--runtime", args.runtime,
                    "--fps", target, "--mode", mode, "--temporal-quality", quality, "--report", str(report),
                ]
                # The outer worker check owns the process group and timeout.
                adapter_process(command)
                actual = json.loads(report.read_text())
                with av.open(str(result)) as output:
                    times = [Fraction(f.pts) * f.time_base for f in output.decode(video=0)]
                    if len(times) != math.ceil(end * FPS[target]) or any(
                        abs(time - index / FPS[target]) > Fraction(1, 1000)
                        for index, time in enumerate(times)
                    ) or abs(Fraction(output.duration, av.time_base) - end) > Fraction(3, 2000):
                        raise ValueError("DLSSG settings check failed frame cadence/duration validation.")
                checked["settings"].append([mode, quality])
                checked["maximum_factor"] = actual["maximum_factor"]
                result.unlink()
                report.unlink()
                atomic_private_json(Path(args.verify_settings), checked)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--library", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--fps", choices=tuple(FPS), default="60")
    parser.add_argument("--mode", choices=("auto", "native", "cascade"), default="auto")
    parser.add_argument("--temporal-quality", choices=("high", "medium", "low"), default="high")
    parser.add_argument("--codec", choices=("h264", "hevc", "av1", "ffv1"), default="h264")
    parser.add_argument("--quality", type=int, choices=range(52), default=20)
    parser.add_argument("--report", help="Write timing and native-pass details to a private job report")
    parser.add_argument("--source-end-time", type=Fraction, help="Measured original video end before lossless transport")
    parser.add_argument("--verify-settings", help="Write actual mode/motion render-check results")
    args = parser.parse_args()
    if args.verify_settings:
        verify_settings(args)
    else:
        render(args)


if __name__ == "__main__":
    main()
