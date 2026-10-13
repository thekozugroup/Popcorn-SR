import hashlib
import json
import math
import subprocess
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

from .dlss import scale_for_recipe

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".mov", ".avi", ".webm", ".m4v", ".ts", ".m2ts", ".mpg", ".mpeg"}


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


@lru_cache(maxsize=1)
def pixel_bit_depths():
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_pixel_formats", "-of", "json"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return {
        p["name"]: max((c.get("bit_depth", 0) for c in p.get("components", [])), default=0)
        for p in json.loads(result.stdout)["pixel_formats"]
    }


def probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path.resolve()),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise ValueError("Cannot read this video. Check that it is complete and supported by FFmpeg.")
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        ),
        None,
    )
    if not video:
        raise ValueError("This file has no playable video stream.")
    duration = float(data.get("format", {}).get("duration", video.get("duration", 0)))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Video duration is missing or invalid.")
    width, height = int(video["width"]), int(video["height"])
    if width <= 0 or height <= 0 or width > 16384 or height > 16384:
        raise ValueError("Video dimensions are outside the supported range.")
    return {
        "width": width,
        "height": height,
        "duration": duration,
        "frame_rate": video.get("avg_frame_rate", "0/0"),
        "video_start_time": video.get("start_time"),
        "start_time": data.get("format", {}).get("start_time"),
        "codec": video.get("codec_name"),
        "pix_fmt": video.get("pix_fmt", ""),
        "bit_depth": pixel_bit_depths().get(video.get("pix_fmt", ""), 0),
        "color_transfer": video.get("color_transfer", "unknown"),
        "color_primaries": video.get("color_primaries", "unknown"),
        "hdr": video.get("color_transfer") in {"smpte2084", "arib-std-b67"},
        "audio_streams": sum(s.get("codec_type") == "audio" for s in streams),
        "subtitle_streams": sum(s.get("codec_type") == "subtitle" for s in streams),
        "attachment_streams": sum(s.get("codec_type") == "attachment" for s in streams),
        "size": path.stat().st_size,
    }


def inspect_source(path: Path):
    before = path.stat()
    info = probe(path)
    info["sha256"] = sha256(path)
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ValueError("Source changed during inspection. Try again when the file has finished copying.")
    info["mtime_ns"] = after.st_mtime_ns
    return info


def dimensions(source, recipe):
    alignment = 8 if recipe["engine"] == "rtx-vsr" else 2
    scale = scale_for_recipe(recipe)
    return tuple(math.ceil(source[k] * scale / alignment) * alignment for k in ("width", "height"))


def validate_output(path: Path, source: dict, recipe: dict):
    info = probe(path)
    expected = (
        min(source["duration"], recipe["preview_seconds"])
        if recipe["preview_seconds"]
        else source["duration"]
    )
    if abs(info["duration"] - expected) > max(0.5, expected * 0.01):
        raise ValueError("Output duration differs from the source. Original preserved; result rejected.")
    if recipe["engine"] != "dlss5" and (info["width"], info["height"]) != dimensions(source, recipe):
        raise ValueError("Output size does not match the requested enhancement.")
    if recipe["engine"] == "dlss5" and (info["width"], info["height"]) != (source["width"], source["height"]):
        raise ValueError("DLSS 5 output unexpectedly changed video dimensions.")
    expected_codec = {"h264": "h264", "hevc": "hevc", "av1": "av1"}[recipe["codec"]]
    if info["codec"] != expected_codec:
        raise ValueError("Output codec differs from the selected codec.")
    if recipe.get("frame_generation"):
        from .frame_generation import FPS

        try:
            actual_rate = Fraction(info["frame_rate"])
        except (ValueError, ZeroDivisionError):
            raise ValueError("Generated output has no valid frame rate.") from None
        if actual_rate != FPS[recipe.get("frame_rate", "60")]:
            raise ValueError("Generated output frame rate differs from the requested cadence.")
    for key in ("audio_streams", "subtitle_streams", "attachment_streams"):
        if info[key] != source[key]:
            raise ValueError(f"Output lost {key.replace('_', ' ')}. Original preserved; result rejected.")
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(path.resolve()),
            "-t",
            "2",
            "-map",
            "0:v:0",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        timeout=60,
    )
    if result.returncode:
        raise ValueError("Output failed its playback check. Original preserved; result rejected.")
    info["sha256"] = sha256(path)
    return info


def ffmpeg_command(source: Path, output: Path, recipe: dict, info: dict, *, video_only=False):
    filters = []
    if recipe["deinterlace"]:
        filters.append("bwdif=mode=send_frame:parity=auto:deint=all")
    if recipe["denoise"]:
        filters.append("hqdn3d=1.5:1.5:6:6")
    width, height = dimensions(info, recipe)
    filters.append(f"scale={width}:{height}:flags=lanczos")
    if recipe["sharpen"]:
        filters.append("unsharp=5:5:0.5:5:5:0")
    if recipe["interpolate"]:
        filters.append("minterpolate=fps=60:mi_mode=mci")
    codec = {"h264": "libx264", "hevc": "libx265", "av1": "libsvtav1", "ffv1": "ffv1"}[recipe["codec"]]
    encoding = [
        "-c:v",
        codec,
        "-crf",
        str(recipe["quality"]),
        "-preset",
        "6" if recipe["codec"] == "av1" else "medium",
    ]
    if recipe["codec"] == "ffv1":
        encoding = ["-c:v", "ffv1", "-level", "3", "-pix_fmt", "bgr0"]
    elif recipe["encoder"] == "nvidia":
        encoding = [
            "-c:v",
            {"h264": "h264_nvenc", "hevc": "hevc_nvenc", "av1": "av1_nvenc"}[recipe["codec"]],
            "-preset",
            "p6",
            "-rc",
            "vbr",
            "-cq",
            str(recipe["quality"]),
            "-b:v",
            "0",
        ]
    preservation = [] if video_only else [
        "-map", "0:a?", "-map", "0:s?", "-map", "0:t?",
        "-map_metadata", "0", "-map_chapters", "0", "-c:a", "copy", "-c:s", "copy", "-c:t", "copy",
    ]
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostdin",
        "-v",
        "error",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(source.resolve()),
        "-map",
        "0:V:0",
        *preservation,
        "-vf",
        ",".join(filters),
        *encoding,
        "-pix_fmt", "bgr0" if recipe["codec"] == "ffv1" else "yuv420p",
        "-fps_mode", "passthrough",
    ]
    if recipe["preview_seconds"]:
        cmd += ["-t", str(recipe["preview_seconds"])]
    return [*cmd, "-progress", "pipe:1", "-n", str(output.resolve())]


def preserved_command(rendered, source, output, recipe, info, timing=None):
    timing_options, duration_options = [], []
    if timing is not None:
        if info.get("video_start_time") is None or info.get("start_time") is None:
            raise ValueError("Original stream offsets are unavailable; refusing to guess synchronization.")
        offset = Fraction(info["video_start_time"]) - Fraction(info["start_time"])
        timing_options = ["-copyts", "-start_at_zero", "-itsoffset", str(float(offset))]
        end = Fraction(timing["source_video_duration"]) + offset
        duration_options = ["-bsf:v", f"setts=duration='max(ceil(0.001/TB),min(DURATION,max(0,({end.numerator}/{end.denominator})/TB-PTS)))'"]
    command = [
        "ffmpeg", "-v", "error", "-nostdin", *timing_options, "-i", str(rendered), "-i", str(source),
        "-map", "0:V:0", "-map", "1:a?", "-map", "1:s?", "-map", "1:t?",
        "-map_metadata", "1", "-map_chapters", "1", "-c", "copy", *duration_options,
    ]
    if recipe["preview_seconds"]:
        command += ["-t", str(recipe["preview_seconds"])]
    return [*command, "-n", str(output)]
