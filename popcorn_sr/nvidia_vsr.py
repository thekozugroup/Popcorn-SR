"""Optional Linux NVIDIA VFX adapter. Streams frames; never writes image sequences.

Uses the public nvvfx API documented by NVIDIA's MIT-licensed Python samples.
The NVIDIA SDK and models are installed separately under their own licenses.
"""

import argparse
from fractions import Fraction

from .video_pipe import encoded_video, nvidia_options


def main():
    parser = argparse.ArgumentParser(description="Popcorn SR NVIDIA Video Super Resolution adapter")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--codec", choices=["h264", "hevc", "av1"], default="h264")
    parser.add_argument("--quality", type=int, choices=range(16, 33), default=23)
    args = parser.parse_args()
    import av
    import torch
    from nvvfx import VideoSuperRes

    if not torch.cuda.is_available():
        raise RuntimeError("NVIDIA CUDA is unavailable. Check the driver and CUDA-enabled PyTorch.")
    torch.cuda.set_device(0)
    with av.open(args.input) as source:
        video = next(s for s in source.streams.video if not (s.disposition.value & 1024))
        if not video.average_rate:
            raise RuntimeError("Frame rate unavailable. Refusing to guess video timing.")
        with encoded_video(
            args.output, args.width, args.height, video.average_rate, video.time_base,
            nvidia_options(args.codec, args.quality),
        ) as (output, encoded):
            with VideoSuperRes(device=0, quality=VideoSuperRes.QualityLevel.HIGH) as effect:
                effect.input_width = video.codec_context.width
                effect.input_height = video.codec_context.height
                effect.output_width, effect.output_height = args.width, args.height
                effect.load()
                if not effect.is_loaded:
                    raise RuntimeError("NVIDIA VFX model did not load.")
                first_pts = None
                for frame in source.decode(video):
                    if frame.pts is None or frame.time_base is None:
                        raise RuntimeError("Frame timestamps unavailable. Refusing to change video timing.")
                    if first_pts is None:
                        first_pts = frame.pts
                    rgb = (
                        torch.from_numpy(frame.to_ndarray(format="rgb24"))
                        .to("cuda:0")
                        .permute(2, 0, 1)
                        .float()
                        .div_(255)
                        .contiguous()
                    )
                    enhanced = torch.from_dlpack(
                        effect.run(rgb, stream_ptr=torch.cuda.current_stream().cuda_stream).image
                    ).clone()
                    if enhanced.ndim != 3 or enhanced.shape[0] != 3 or enhanced.dtype != torch.float32:
                        raise RuntimeError("NVIDIA VFX returned an unexpected frame format.")
                    pixels = (
                        enhanced.clamp(0, 1)
                        .mul(255)
                        .round()
                        .byte()
                        .permute(1, 2, 0)
                        .contiguous()
                        .cpu()
                        .numpy()
                    )
                    result = av.VideoFrame.from_ndarray(pixels, format="rgb24")
                    result.pts = frame.pts - first_pts
                    result.time_base = Fraction(frame.time_base)
                    for field in ("colorspace", "color_primaries", "color_trc", "color_range"):
                        value = getattr(frame, field, None)
                        if value is not None:
                            setattr(result, field, value)
                    for packet in encoded.encode(result):
                        output.mux(packet)
                    print(
                        f"out_time_us={int((frame.pts - first_pts) * frame.time_base * 1_000_000)}",
                        flush=True,
                    )


if __name__ == "__main__":
    main()
