import hashlib
import json
import math
import subprocess
from pathlib import Path

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".mov", ".avi", ".webm", ".m4v", ".ts", ".m2ts", ".mpg", ".mpeg"}


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


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
        "codec": video.get("codec_name"),
        "pix_fmt": video.get("pix_fmt", ""),
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
    return tuple(math.ceil(source[k] * recipe["scale"] / alignment) * alignment for k in ("width", "height"))


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


def ffmpeg_command(source: Path, output: Path, recipe: dict, info: dict):
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
    codec = {"h264": "libx264", "hevc": "libx265", "av1": "libsvtav1"}[recipe["codec"]]
    encoding = [
        "-c:v",
        codec,
        "-crf",
        str(recipe["quality"]),
        "-preset",
        "6" if recipe["codec"] == "av1" else "medium",
    ]
    if recipe["encoder"] == "nvidia":
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
        "-map",
        "0:a?",
        "-map",
        "0:s?",
        "-map",
        "0:t?",
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
        "-vf",
        ",".join(filters),
        *encoding,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-c:s",
        "copy",
        "-c:t",
        "copy",
    ]
    if recipe["preview_seconds"]:
        cmd += ["-t", str(recipe["preview_seconds"])]
    return [*cmd, "-progress", "pipe:1", "-n", str(output.resolve())]
