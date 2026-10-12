"""Optional Real-ESRGAN x4plus video restoration with bounded GPU tiles."""

import argparse
from fractions import Fraction

from .media import sha256

MODEL_SHA256 = "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"


def restore_tiled(model, frame, width, height, tile=192, padding=24):
    import torch
    from torch.nn import functional as F

    _, _, h, w = frame.shape
    output = frame.new_empty((1, 3, h * 4, w * 4))
    with torch.inference_mode():
        for y in range(0, h, tile):
            for x in range(0, w, tile):
                end_x, end_y = min(x + tile, w), min(y + tile, h)
                left, top = max(x - padding, 0), max(y - padding, 0)
                right, bottom = min(end_x + padding, w), min(end_y + padding, h)
                restored = model(frame[:, :, top:bottom, left:right])
                output[:, :, y * 4 : end_y * 4, x * 4 : end_x * 4] = restored[
                    :, :, (y - top) * 4 : (end_y - top) * 4, (x - left) * 4 : (end_x - left) * 4
                ]
        return F.interpolate(output, size=(height, width), mode="bicubic", align_corners=False).clamp(0, 1)


def main():
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Real-ESRGAN video adapter")
    for key in ("input", "output", "model"):
        parser.add_argument(f"--{key}", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--codec", choices=["h264", "hevc", "av1"], default="h264")
    args = parser.parse_args()
    if sha256(Path(args.model)) != MODEL_SHA256:
        raise RuntimeError("Model checksum mismatch. Use the official RealESRGAN_x4plus checkpoint.")
    import av
    import torch

    from .rrdbnet import RRDBNet

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable. Install a PyTorch runtime compatible with this GPU.")
    model = RRDBNet(3, 3)
    checkpoint = torch.load(args.model, map_location="cpu", weights_only=True)
    model.load_state_dict(checkpoint.get("params_ema", checkpoint.get("params")), strict=True)
    model = model.eval().to("cuda").half()
    with av.open(args.input) as source, av.open(args.output, mode="w", format="matroska") as output:
        video = next(s for s in source.streams.video if not s.disposition.attached_pic)
        if not video.average_rate:
            raise RuntimeError("Frame rate unavailable; refusing to guess timing.")
        encoded = output.add_stream(f"{args.codec}_nvenc", rate=video.average_rate)
        encoded.width, encoded.height = args.width, args.height
        encoded.pix_fmt = "yuv420p"
        encoded.time_base = video.time_base
        encoded.options = {"preset": "p6", "rc": "vbr", "cq": "20", "b": "0"}
        encoded.codec_context.open()
        first = None
        for frame in source.decode(video):
            if frame.pts is None or frame.time_base is None:
                raise RuntimeError("Missing frame timestamps; refusing to change timing.")
            first = frame.pts if first is None else first
            pixels = (
                torch.from_numpy(frame.to_ndarray(format="rgb24"))
                .to("cuda")
                .permute(2, 0, 1)
                .unsqueeze(0)
                .half()
                .div_(255)
            )
            enhanced = restore_tiled(model, pixels, args.width, args.height)
            image = enhanced.squeeze(0).mul(255).round().byte().permute(1, 2, 0).contiguous().cpu().numpy()
            result = av.VideoFrame.from_ndarray(image, format="rgb24")
            result.pts, result.time_base = frame.pts - first, Fraction(frame.time_base)
            for packet in encoded.encode(result):
                output.mux(packet)
            print(f"out_time_us={int((frame.pts - first) * frame.time_base * 1_000_000)}", flush=True)
        for packet in encoded.encode(None):
            output.mux(packet)


if __name__ == "__main__":
    main()
