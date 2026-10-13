"""Actual separately installed NVIDIA VFX TrueHDR, with timestamped 10-bit export.

The optional runtime/models retain NVIDIA's license. The API contract is
documented in NVIDIA-Maxine/nvidia-vfx-python-samples (MIT). Nothing is bundled.
"""

import argparse
import sys
from fractions import Fraction
from pathlib import Path

from .frame_generation import source_timeline
from .hdr import RGB10_COLOR, hdr_encoding_options, packed_hdr_frame, validate_hdr
from .media import probe
from .video_pipe import encoded_video


def bounded_int(low, high):
    def parse(value):
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError("Enter a whole number.") from None
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"Choose a value from {low} to {high}.")
        return number
    return parse


def main():
    parser = argparse.ArgumentParser(description="NVIDIA TrueHDR video conversion; no CPU fallback")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--codec", choices=["hevc", "av1"], default="hevc")
    parser.add_argument("--quality", type=int, choices=range(16, 33), default=23)
    parser.add_argument("--contrast", type=bounded_int(0, 200), metavar="0..200", default=100)
    parser.add_argument("--saturation", type=bounded_int(0, 200), metavar="0..200", default=100)
    parser.add_argument("--middle-gray", type=bounded_int(10, 100), metavar="10..100", default=50)
    parser.add_argument("--luminance", type=bounded_int(400, 2000), metavar="400..2000", default=650)
    parser.add_argument("--debanding-off", action="store_true")
    parser.add_argument("--end-time", type=Fraction, help="Exact video duration from a preceding generation pass")
    args = parser.parse_args()
    info = probe(args.input)
    if info["hdr"] or info["bit_depth"] != 8:
        raise ValueError("TrueHDR accepts 8-bit SDR input; existing HDR/high-bit-depth sources are unsupported.")
    if info["width"] % 2 or info["height"] % 2:
        raise ValueError("10-bit 4:2:0 export requires even dimensions.")
    timing = source_timeline(args.input)
    end = args.end_time if args.end_time is not None else timing["duration"]
    # NUT retains dense picture timestamps but can lose the final packet's
    # duration. A preceding stage supplies the independently measured end.
    if not timing["last_frame_time"] < end:
        raise ValueError("HDR end time does not match the source picture timeline.")
    import av
    import torch
    from nvvfx import TrueHDR

    if not torch.cuda.is_available():
        raise RuntimeError("TrueHDR requires a compatible NVIDIA VFX runtime and CUDA device.")
    torch.cuda.set_device(0)
    effect = TrueHDR(device=0, contrast=args.contrast, saturation=args.saturation,
                     middle_gray=args.middle_gray, luminance=args.luminance,
                     debanding_off=int(args.debanding_off))
    try:
        effect.load()
        if not effect.is_loaded:
            raise RuntimeError("NVIDIA TrueHDR did not load; verify the separately installed model/runtime.")
        with av.open(args.input, options={"protocol_whitelist": "file,pipe"}) as source:
            video = next(s for s in source.streams.video if not (s.disposition.value & 1024))
            if not video.average_rate or not video.time_base or video.sample_aspect_ratio not in (None, 1):
                raise ValueError("TrueHDR needs known video timing and square pixels.")
            with encoded_video(args.output, info["width"], info["height"], video.average_rate,
                               video.time_base, hdr_encoding_options(args.codec, args.quality),
                               end_time=end, final_frame_time=timing["last_frame_time"],
                               input_pix_fmt="gbrp10le", color_metadata=RGB10_COLOR) as (output, stream):
                first, last = None, None
                frames = 0
                for frame in source.decode(video):
                    if frame.pts is None or frame.time_base is None:
                        raise ValueError("TrueHDR input is missing frame timestamps.")
                    timestamp = frame.pts * Fraction(frame.time_base)
                    if last is not None and timestamp <= last:
                        raise ValueError("TrueHDR input timestamps are not increasing.")
                    first = timestamp if first is None else first
                    last = timestamp
                    rgb = torch.from_numpy(frame.to_ndarray(format="rgb24")).to("cuda:0")
                    rgb = rgb.permute(2, 0, 1).float().div_(255).contiguous()
                    pixels = torch.from_dlpack(effect.run(rgb, stream_ptr=torch.cuda.current_stream().cuda_stream).image).clone()
                    if pixels.dtype != torch.uint32 or tuple(pixels.shape) != (info["height"], info["width"]):
                        raise RuntimeError("TrueHDR returned an unexpected format; 10-bit packed output is required.")
                    result = packed_hdr_frame(pixels.cpu().numpy())
                    tick = (timestamp - first) / Fraction(video.time_base)
                    if tick.denominator != 1:
                        raise ValueError("TrueHDR cannot represent source timing without rounding.")
                    result.pts, result.time_base = tick.numerator, Fraction(video.time_base)
                    for packet in stream.encode(result):
                        output.mux(packet)
                    frames += 1
                    print(f"out_time_us={int((timestamp - first) * 1_000_000)}", flush=True)
                if not frames:
                    raise ValueError("TrueHDR input contains no decoded pictures.")
                if frames != timing["frames"] or last - first != timing["last_frame_time"]:
                    raise ValueError("HDR source timeline changed during processing.")
        validate_hdr(probe(args.output))
    finally:
        failed = sys.exception()
        try:
            effect.close()
        except Exception as exc:
            if failed is None:
                raise
            failed.add_note(f"TrueHDR cleanup also failed: {type(exc).__name__}")


if __name__ == "__main__":
    main()
