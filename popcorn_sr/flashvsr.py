"""Pinned, optional FlashVSR+ temporal restoration with Popcorn's media transport.

The operator supplies the Apache-2.0 runtime and verified model weights.
Only bounded picture groups enter the model. No image sequence or lossy
intermediate is written; compression and media preservation remain separate.
"""

import argparse
import json
import os
import sys
import tempfile
from collections import deque
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path

from .frame_generation import source_timeline
from .media import probe, sha256
from .nvidia_vsr import validate_render
from .restoration_assets import MODEL_HASHES, RUNTIME_REVISION
from .sdr import SDRColor
from .video_pipe import encoded_video, nvidia_options


def padded_size(width, height):
    if not all(type(v) is int and 64 <= v <= 7680 and v % 2 == 0 for v in (width, height)):
        raise ValueError("Restoration needs even output dimensions between 64 and 7680 pixels.")
    return ((width + 127) // 128 * 128, (height + 127) // 128 * 128)


def verify_runtime(root, models):
    if (root / ".popcorn-revision").read_text().strip() != RUNTIME_REVISION:
        raise ValueError("FlashVSR+ runtime revision differs from the verified Popcorn adapter.")
    for filename, expected in MODEL_HASHES.items():
        if sha256(models / filename) != expected:
            raise ValueError(f"FlashVSR+ checkpoint checksum mismatch: {filename}")


class PictureClock:
    """Bounded lookahead connects each model picture to its original timestamp."""

    def __init__(self, time_base):
        self.time_base = Fraction(time_base)
        self.first = self.previous = None
        self.pending = deque()
        self.read = self.written = self.peak = 0

    def push(self, pts, time_base):
        if pts is None or time_base is None:
            raise ValueError("Restoration source picture timestamp is missing.")
        timestamp = Fraction(pts) * time_base
        if self.previous is not None and timestamp <= self.previous:
            raise ValueError("Restoration source timestamps must increase.")
        self.first = timestamp if self.first is None else self.first
        ticks = (timestamp - self.first) / self.time_base
        if ticks.denominator != 1:
            raise ValueError("Restoration source timestamp is outside its declared clock.")
        self.pending.append(int(ticks))
        self.previous, self.read = timestamp, self.read + 1
        self.peak = max(self.peak, len(self.pending))
        if self.peak > 65:
            raise ValueError("Restoration exceeded its bounded picture lookahead.")

    def take(self):
        if not self.pending:
            raise ValueError("Restoration generated extra pictures.")
        self.written += 1
        return self.pending.popleft()

    def finish(self, timing):
        if (self.pending or self.read != timing["frames"] or self.written != timing["frames"]
                or self.previous is None or self.previous - self.first != timing["last_frame_time"]):
            raise ValueError("Restoration changed the source picture count or timeline.")


@contextmanager
def resident_weights(module):
    """Avoid copying weights to CPU immediately before decoding a segment.

    This is a pinned upstream extension point, isolated in one job subprocess.
    The CUDA allocator has a separate memory ceiling; insufficient memory fails
    rather than silently moving the job to CPU or affecting another service.
    """
    original = module._offload_dit

    def keep(bundle, state, device):
        if device.type != "cuda" or state.attention_cache_offload_layers:
            raise ValueError("Restoration requires the verified CUDA resident-weight policy.")
        if state.attention_cache_transfer_stream is not None:
            state.attention_cache_transfer_stream.synchronize()

    module._offload_dit = keep
    try:
        yield
    finally:
        module._offload_dit = original


@contextmanager
def job_cache(parent):
    keys = ("HOME", "TMPDIR", "XDG_CACHE_HOME", "CUDA_CACHE_PATH", "TRITON_CACHE_DIR",
            "TORCHINDUCTOR_CACHE_DIR", "TORCH_EXTENSIONS_DIR", "MPLCONFIGDIR",
            "HF_HOME", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
    previous = {key: os.environ.get(key) for key in keys}
    try:
        with tempfile.TemporaryDirectory(prefix="flash-cache-", dir=parent) as folder:
            os.environ.update(dict.fromkeys(keys, folder))
            os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
            yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def input_chunks(source, video, color, clock, width, height, padded):
    import torch
    from torch.nn import functional as F

    frames, limit = [], 17
    incoming_size = (video.width, video.height)
    for frame in source.decode(video):
        if (frame.width, frame.height) != incoming_size:
            raise ValueError("Restoration source dimensions changed during decoding.")
        clock.push(frame.pts, frame.time_base)
        rgb = torch.from_numpy(color.rgb(frame)).to("cuda").permute(2, 0, 1).unsqueeze(0).float().div_(255)
        rgb = F.interpolate(rgb, size=(height, width), mode="bicubic", align_corners=False).clamp_(0, 1)
        # Pad, then crop the generated picture. Never crop the source to a new aspect ratio.
        rgb = F.pad(rgb, (0, padded[0] - width, 0, padded[1] - height), mode="replicate")
        frames.append(rgb.squeeze(0).mul_(2).sub_(1).to(torch.bfloat16))
        if len(frames) == limit:
            yield torch.stack(frames, dim=1).unsqueeze(0)
            frames, limit = [], 16
    if frames:
        yield torch.stack(frames, dim=1).unsqueeze(0)


class FrameWriter:
    def __init__(self, output, stream, clock, width, height, padded):
        self.output, self.stream, self.clock = output, stream, clock
        self.width, self.height, self.padded = width, height, padded

    def append(self, pictures):
        import av
        import torch

        if (pictures.ndim != 5 or pictures.shape[:2] != (1, 3)
                or tuple(pictures.shape[-2:]) != self.padded[::-1]):
            raise ValueError("Restoration returned unexpected picture dimensions.")
        for tensor in pictures[0].permute(1, 0, 2, 3):
            if not torch.isfinite(tensor).all().item():
                raise ValueError("Restoration returned non-finite pixels.")
            rgb = tensor[:, :self.height, :self.width].detach().float().add(1).mul_(127.5)
            pixels = rgb.clamp_(0, 255).round_().byte().permute(1, 2, 0).contiguous().cpu().numpy()
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            frame.pts, frame.time_base = self.clock.take(), self.clock.time_base
            for packet in self.stream.encode(frame):
                self.output.mux(packet)
            print(f"out_time_us={int(frame.pts * frame.time_base * 1_000_000)}", flush=True)


def _render(args):
    padded = padded_size(args.width, args.height)
    verify_runtime(args.runtime, args.models)
    info = probe(args.input)
    if info["hdr"] or info["bit_depth"] != 8:
        raise ValueError("Restoration accepts 8-bit SDR; HDR and high-bit-depth originals are protected.")
    timing = source_timeline(args.input)
    color = SDRColor.read(args.input)
    import av
    import torch

    if not torch.cuda.is_available():
        raise ValueError("FlashVSR+ requires a compatible CUDA GPU; no CPU fallback is used.")
    torch.cuda.set_device(0)
    free, total = torch.cuda.mem_get_info()
    budget = min(20 * 1024**3, int(free * .6), int(total * .85))
    if budget < 4 * 1024**3:
        raise ValueError("Insufficient free GPU memory for restoration. Free memory or choose another method.")
    torch.cuda.set_per_process_memory_fraction(budget / total)
    sys.path[:0] = [str(args.runtime), str(args.runtime / "operators/flashvsr_attn")]
    from inference import build_inference_pipeline
    from inference.loading import ModelPaths
    from inference.preprocessing import TemporalVideoStream
    from inference.presets import stream_config_for_mode
    from inference.randomness import set_inference_seed
    from inference.runners import stream as upstream_stream

    set_inference_seed(42)
    config = stream_config_for_mode(
        "turbo", seed=42, decode_every=4, attn_kernel="triton_block_sparse",
        hardware_profile="auto", cache_offload_mode="never", color_correction=True,
        tiny_decoder_mode="serial",
    )
    paths = ModelPaths(
        dit=str(args.models / "turbo/dit.safetensors"),
        lq_projection=str(args.models / "turbo/lq_proj_in.safetensors"),
        tiny_decoder=str(args.models / "TCDecoder.ckpt"),
        context=str(args.runtime / "prompt_tensor/posi_prompt.pth"),
    )
    pipeline = build_inference_pipeline(config, paths)
    clock = PictureClock(timing["time_base"])
    with av.open(str(args.input), options={"protocol_whitelist": "file,pipe"}) as source:
        video = next(s for s in source.streams.video if not (s.disposition.value & 1024))
        video.codec_context.thread_count = 2
        if not video.average_rate or not video.time_base or video.sample_aspect_ratio not in (None, 1):
            raise ValueError("Restoration needs known timing and square source pixels.")
        pictures = TemporalVideoStream(input_chunks(source, video, color, clock, args.width, args.height, padded), 4)
        try:
            with encoded_video(
                str(args.output), args.width, args.height, timing["rate"], timing["time_base"],
                nvidia_options(args.codec, args.quality), end_time=timing["duration"],
                final_frame_time=timing["last_frame_time"], sdr_color=color,
            ) as (output, stream), resident_weights(upstream_stream):
                writer = FrameWriter(output, stream, clock, args.width, args.height, padded)
                pipeline.runner.run(pictures, None, segment_writer=writer)
                clock.finish(timing)
        finally:
            pictures.close()
    validate_render(args.input, args.output, args.width, args.height, args.codec)
    print("restoration_report=" + json.dumps({
        "frames": clock.written, "peak_clock_lookahead": clock.peak,
        "peak_buffered_pictures": pictures.max_buffer_frames,
        "cuda_peak_bytes": torch.cuda.max_memory_allocated(),
    }), flush=True)


def render(args):
    if args.output.exists() or args.output.is_symlink():
        raise FileExistsError("Choose a new restoration output; existing files are preserved.")
    # Encode privately, then publish without replacing a concurrent file.
    # FFmpeg itself also refuses an existing path. Failed files and all caches
    # disappear with this directory, including when validation fails.
    with tempfile.TemporaryDirectory(prefix="flash-result-", dir=args.output.parent) as folder:
        target = Path(folder) / args.output.name
        work = argparse.Namespace(**(vars(args) | {"output": target}))
        with job_cache(Path(folder)):
            _render(work)
        os.link(target, args.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("input", "output", "runtime", "models"):
        parser.add_argument(f"--{key}", required=True, type=Path)
    parser.add_argument("--width", required=True, type=int)
    parser.add_argument("--height", required=True, type=int)
    parser.add_argument("--codec", choices=("h264", "hevc", "av1"), default="h264")
    parser.add_argument("--quality", type=int, choices=range(16, 33), default=23)
    args = parser.parse_args()
    render(args)


if __name__ == "__main__":
    main()
