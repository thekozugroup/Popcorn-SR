"""Scratch planning for the current whole-video lossless generation pipeline."""

import math
from fractions import Fraction

from .frame_generation import FPS, plan_factors
from .media import dimensions


def estimate_scratch_bytes(source, recipe, capabilities):
    """Include coexisting lossless passes, not just the compressed input size.

    Raw BGRA plus container/headroom is deliberately conservative: actual FFV1
    compression varies with content. Runtime drive/space checks remain necessary.
    """
    baseline = int(source["size"]) * 4
    if not recipe.get("frame_generation") and not recipe.get("hdr"):
        return baseline
    try:
        duration = Fraction(str(source["duration"]))
        if recipe.get("preview_seconds"):
            duration = min(duration, recipe["preview_seconds"])
        rate = Fraction(source["frame_rate"])
        target = FPS[recipe.get("frame_rate", "60")] if recipe.get("frame_generation") else rate
        factors = plan_factors(
            rate, target, capabilities.get("dlss_frame_generation", {}).get("maximum_factor", 0),
            recipe.get("frame_generation_mode", "auto"),
        ) if recipe.get("frame_generation") else ()
        if duration <= 0 or rate <= 0:
            raise ValueError("Duration must be positive.")
        width, height = dimensions(source, recipe)
    except (ValueError, ZeroDivisionError, KeyError, TypeError) as exc:
        stage = "generation" if recipe.get("frame_generation") else "HDR"
        raise ValueError(f"Cannot estimate {stage} storage. Verify source timing and worker support.") from exc

    def lossless(frames, w=width, h=height):
        # Four-channel 8-bit frames, packet overhead, and 25% encoding headroom.
        return math.ceil(Fraction(frames * (w * h * 4 + 4096) * 5, 4)) + 65536

    frames = math.ceil(rate * duration) + 2
    base = baseline + lossless(frames)  # Initial upscale stays until generation finishes.
    if recipe["engine"] != "resize" and recipe.get("preview_seconds"):
        base += lossless(frames, source["width"], source["height"])
    previous, peak = 0, 0
    for factor in factors:
        frames *= factor
        current = lossless(frames)
        peak = max(peak, previous + current)
        previous = current
    # Final encoding coexists with the final lossless pass. Raw-frame headroom
    # avoids treating a small input bitrate as an output-size guarantee.
    finished = lossless(math.ceil(target * duration) + 2)
    # HDR converts the final lossless SDR pass; conservative 10-bit encoded and
    # remux headroom coexists with it. Avoid reserving only compressed input size.
    hdr_headroom = finished * 2 if recipe.get("hdr") else 0
    return base + max(peak, previous + finished) + hdr_headroom
