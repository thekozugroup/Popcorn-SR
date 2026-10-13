"""Separately installed NVIDIA VFX VSR; no fallback or frame sequences.

Uses the public API in NVIDIA's MIT samples. SDK/models retain their license.
FFmpeg export and timestamp validation are Popcorn SR code.
"""

import argparse
import json
import math
from fractions import Fraction
from itertools import zip_longest
from pathlib import Path

from .frame_generation import source_timeline
from .media import probe
from .video_pipe import encoded_video, encoding_options

QUALITY_NAMES = {1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "ULTRA"}


def strength(value):
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise argparse.ArgumentTypeError("VSR strength must be from 0 to 1.")
    return number


def validate_render(source, output, width, height, codec):
    """Decode every picture and compare the actual clock, with bounded memory."""
    import av

    result = probe(output)
    if (result["width"], result["height"], result["codec"]) != (width, height, codec):
        raise ValueError("VSR returned unexpected dimensions or codec.")
    if result["hdr"] or result["bit_depth"] != 8:
        raise ValueError("VSR changed the expected 8-bit SDR format.")
    timing = source_timeline(source)
    # NUT container duration is the final picture's PTS. Internal lossless
    # transport is checked against every decoded picture timestamp below.
    if codec != "ffv1" and abs(result["duration"] - float(timing["duration"])) > .002:
        raise ValueError("VSR changed video duration.")
    with av.open(source, options={"protocol_whitelist": "file,pipe"}) as incoming, av.open(
        output, options={"protocol_whitelist": "file,pipe"},
    ) as returned:
        a = next(s for s in incoming.streams.video if not (s.disposition.value & 1024))
        b = next(s for s in returned.streams.video if not (s.disposition.value & 1024))
        first_a, first_b = None, None
        for original, enhanced in zip_longest(incoming.decode(a), returned.decode(b)):
            if original is None or enhanced is None or original.pts is None or enhanced.pts is None:
                raise ValueError("VSR changed frame count or omitted timestamps.")
            clock_a, clock_b = Fraction(original.pts) * original.time_base, Fraction(enhanced.pts) * enhanced.time_base
            first_a = clock_a if first_a is None else first_a
            first_b = clock_b if first_b is None else first_b
            if abs((clock_a - first_a) - (clock_b - first_b)) > Fraction(1, 1000):
                raise ValueError("VSR changed picture timestamps.")


def render(args):
    if not all(64 <= value <= 7680 and value % 8 == 0 for value in (args.width, args.height)):
        raise ValueError("VSR output dimensions must be multiples of 8, from 64 to 7680 pixels.")
    info = probe(args.input)
    if info["hdr"] or info["bit_depth"] != 8:
        raise ValueError("VSR accepts 8-bit SDR input; existing HDR/high-bit-depth sources are protected.")
    timing = source_timeline(args.input)
    import av
    import torch
    from nvvfx import VideoSuperRes

    if not torch.cuda.is_available():
        raise RuntimeError("VSR requires a compatible NVIDIA VFX runtime and CUDA device.")
    torch.cuda.set_device(0)
    effect = VideoSuperRes(device=0, quality=VideoSuperRes.QualityLevel[QUALITY_NAMES[args.vsr_quality]],
                           strength=args.strength, image_encoding=VideoSuperRes.ImageEncoding.RGB8)
    try:
        effect.input_width, effect.input_height = info["width"], info["height"]
        effect.output_width, effect.output_height = args.width, args.height
        effect.load()
        if not effect.is_loaded:
            raise RuntimeError("NVIDIA VSR did not load; verify the separately installed model/runtime.")
        with av.open(args.input, options={"protocol_whitelist": "file,pipe"}) as source:
            video = next(s for s in source.streams.video if not (s.disposition.value & 1024))
            if not video.average_rate or not video.time_base or video.sample_aspect_ratio not in (None, 1):
                raise ValueError("VSR needs known video timing and square pixels.")
            metadata = {field: getattr(video.codec_context, field) for field in
                        ("colorspace", "color_primaries", "color_trc", "color_range")}
            with encoded_video(args.output, args.width, args.height, timing["rate"], timing["time_base"],
                               encoding_options(args.codec, args.quality), end_time=timing["duration"],
                               final_frame_time=timing["last_frame_time"], color_metadata=metadata) as (output, stream):
                first, previous, count = None, None, 0
                for frame in source.decode(video):
                    if frame.pts is None or frame.time_base is None:
                        raise ValueError("VSR source timestamps are unavailable.")
                    timestamp = Fraction(frame.pts) * frame.time_base
                    if previous is not None and timestamp <= previous:
                        raise ValueError("VSR source timestamps must increase.")
                    if (frame.width, frame.height) != (info["width"], info["height"]):
                        raise ValueError("VSR source dimensions changed during decoding.")
                    first = timestamp if first is None else first
                    ticks = (timestamp - first) / timing["time_base"]
                    if ticks.denominator != 1:
                        raise ValueError("VSR source timestamp is outside its declared clock.")
                    rgb = torch.from_numpy(frame.to_ndarray(format="rgb24")).to("cuda:0").permute(2, 0, 1).float().div_(255).contiguous()
                    enhanced = torch.from_dlpack(effect.run(rgb, stream_ptr=torch.cuda.current_stream().cuda_stream).image).clone()
                    if tuple(enhanced.shape) != (3, args.height, args.width) or enhanced.dtype != torch.float32:
                        raise RuntimeError("NVIDIA VSR returned unexpected frame dimensions or format.")
                    if not torch.isfinite(enhanced).all().item():
                        raise RuntimeError("NVIDIA VSR returned non-finite pixels.")
                    pixels = enhanced.clamp(0, 1).mul(255).round().byte().permute(1, 2, 0).contiguous().cpu().numpy()
                    result = av.VideoFrame.from_ndarray(pixels, format="rgb24")
                    result.pts, result.time_base = int(ticks), timing["time_base"]
                    for field, value in metadata.items():
                        setattr(result, field, value)
                    for packet in stream.encode(result):
                        output.mux(packet)
                    count += 1
                    previous = timestamp
                    print(f"out_time_us={int((timestamp - first) * 1_000_000)}", flush=True)
                if count != timing["frames"] or previous - first != timing["last_frame_time"]:
                    raise ValueError("VSR source timeline changed during processing.")
        validate_render(args.input, args.output, args.width, args.height, args.codec)
    finally:
        effect.close()


def verify_settings(args):
    """Actual GPU renders of every level/strength, codec and lossless contract."""
    report = Path(args.verify_settings)
    checked = {"qualities": [], "strength": False, "custom_size": False, "codecs": [], "lossless": False}

    def save():
        pending = report.with_suffix(".pending")
        pending.write_text(json.dumps(checked))
        pending.replace(report)

    def check(codec, levels, strengths, width=args.width, height=args.height):
        output = Path(args.output).with_name("vsr-settings.nut" if codec == "ffv1" else "vsr-settings.mkv")
        try:
            for level in levels:
                for amount in strengths:
                    output.unlink(missing_ok=True)
                    render(argparse.Namespace(**(vars(args) | {"output": output, "width": width, "height": height,
                           "codec": codec, "vsr_quality": level, "strength": amount})))
            return True
        except (ValueError, RuntimeError, OSError):
            return False
        finally:
            output.unlink(missing_ok=True)

    save()
    for codec in args.verify_codecs.split(","):
        if check(codec, QUALITY_NAMES, (0, .5, 1)):
            checked["codecs"].append(codec)
            checked["qualities"], checked["strength"] = list(QUALITY_NAMES), True
        save()
    if checked["codecs"]:
        checked["lossless"] = check("ffv1", QUALITY_NAMES, (0, .5, 1))
        checked["custom_size"] = check(checked["codecs"][0], QUALITY_NAMES, (1,), 520, 296)
        save()


def main():
    parser = argparse.ArgumentParser(description="NVIDIA Video Super Resolution; no CPU fallback")
    for key in ("input", "output"):
        parser.add_argument(f"--{key}", required=True, type=Path)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--codec", choices=["h264", "hevc", "av1", "ffv1"], default="h264")
    parser.add_argument("--quality", type=int, choices=range(16, 33), default=23, help="Export compression quality")
    parser.add_argument("--vsr-quality", type=int, choices=QUALITY_NAMES, default=3)
    parser.add_argument("--strength", type=strength, default=1.)
    parser.add_argument("--verify-settings")
    parser.add_argument("--verify-codecs", default="h264")
    args = parser.parse_args()
    if set(args.verify_codecs.split(",")) - {"h264", "hevc", "av1"}:
        parser.error("Choose H.264, HEVC or AV1 verification codecs.")
    if args.verify_settings:
        verify_settings(args)
    else:
        render(args)


if __name__ == "__main__":
    main()
