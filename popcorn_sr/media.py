import hashlib
import json
import math
import subprocess
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

from .dlss import scale_for_recipe

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".mov", ".avi", ".webm", ".m4v", ".ts", ".m2ts", ".mpg", ".mpeg"}


def picture_metadata(path: Path):
    """Read only a video header for visible library rows; never hash/decode media."""
    result = subprocess.run([
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-select_streams", "V:0",
        "-show_entries", "stream=width,height,codec_name", "-of", "json", str(path.resolve()),
    ], capture_output=True, text=True, timeout=15, check=False)
    if result.returncode:
        raise ValueError("Video details unavailable. Check that the file has finished copying.")
    video = next(iter(json.loads(result.stdout).get("streams", [])), None)
    if not video or not 0 < video.get("width", 0) <= 16384 or not 0 < video.get("height", 0) <= 16384:
        raise ValueError("No supported video header was found.")
    return {"width": video["width"], "height": video["height"], "codec": video.get("codec_name")}


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


def first_packet_time(path: Path, selector: str):
    """Inspect the copied packet clock, independent of codec priming metadata."""
    result = subprocess.run([
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
        "-select_streams", selector, "-read_intervals", "%+#1",
        "-show_entries", "packet=pts_time", "-of", "json", str(path.resolve()),
    ], capture_output=True, text=True, timeout=60, check=True)
    packets = json.loads(result.stdout).get("packets", [])
    if not packets or packets[0].get("pts_time") is None:
        raise ValueError("Copied audio packet timing is unavailable; refusing to guess synchronization.")
    return packets[0]["pts_time"]


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
            "-show_chapters",
            "-show_data_hash",
            "sha256",
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
    # Matroska's stream DURATION tag is an end timestamp. Audio preroll can
    # make format.duration much longer than the playable picture sequence.
    picture_duration = video.get("duration")
    if picture_duration is None and video.get("tags", {}).get("DURATION"):
        try:
            hours, minutes, seconds = video["tags"]["DURATION"].split(":")
            picture_duration = float(int(hours) * 3600 + int(minutes) * 60 + Fraction(seconds)
                                     - Fraction(video.get("start_time") or "0"))
        except (ValueError, ZeroDivisionError):
            picture_duration = None
    if picture_duration is None:
        picture_duration = duration - max(0, float(Fraction(video.get("start_time") or "0")
                                                   - Fraction(data.get("format", {}).get("start_time") or "0")))
    picture_duration = float(picture_duration)
    if not math.isfinite(picture_duration) or picture_duration <= 0:
        raise ValueError("Picture duration is missing or invalid.")
    return {
        "width": width,
        "height": height,
        "duration": duration,
        "video_duration": picture_duration,
        "frame_rate": video.get("avg_frame_rate", "0/0"),
        "video_start_time": video.get("start_time"),
        "start_time": data.get("format", {}).get("start_time"),
        "codec": video.get("codec_name"),
        "pix_fmt": video.get("pix_fmt", ""),
        "bit_depth": pixel_bit_depths().get(video.get("pix_fmt", ""), 0),
        "color_transfer": video.get("color_transfer", "unknown"),
        "color_primaries": video.get("color_primaries", "unknown"),
        "color_space": video.get("color_space", "unknown"),
        "color_range": video.get("color_range", "unknown"),
        "hdr": video.get("color_transfer") in {"smpte2084", "arib-std-b67"},
        "audio_streams": sum(s.get("codec_type") == "audio" for s in streams),
        "subtitle_streams": sum(s.get("codec_type") == "subtitle" for s in streams),
        "attachment_streams": sum(s.get("codec_type") == "attachment" for s in streams),
        "preservation": {
            "audio": [
                {"codec": s.get("codec_name"), "start_time": s.get("start_time"),
                 "first_packet_time": first_packet_time(path, f"a:{index}")}
                for index, s in enumerate(s for s in streams if s.get("codec_type") == "audio")
            ],
            "chapters": [
                {k: c.get(k) for k in ("start_time", "end_time", "tags")}
                for c in data.get("chapters", [])
            ],
            "attachments": [
                {"sha256": s.get("extradata_hash"), "tags": s.get("tags", {})}
                for s in streams if s.get("codec_type") == "attachment"
            ],
            "title": data.get("format", {}).get("tags", {}).get("title"),
        },
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
    if recipe.get("target_resolution") is not None:
        from .resolution import target_dimensions

        return target_dimensions(source, recipe["target_resolution"], 8 if recipe["engine"] == "rtx-vsr" else 2)
    if recipe["engine"] == "rtx-vsr" and recipe.get("output_width") is not None:
        return recipe["output_width"], recipe["output_height"]
    alignment = 8 if recipe["engine"] == "rtx-vsr" else 2
    scale = scale_for_recipe(recipe)
    return tuple(math.ceil(source[k] * scale / alignment) * alignment for k in ("width", "height"))


def preview_duration(source, recipe):
    duration = video_duration(source) if recipe.get("preview_frame_time") is not None else source["duration"]
    remaining = duration - (recipe.get("preview_frame_time") or 0)
    return min(remaining, recipe["preview_seconds"]) if recipe["preview_seconds"] else source["duration"]


def video_duration(source):
    """Support earlier stored jobs without confusing audio preroll with pictures."""
    return source.get("video_duration", source["duration"] - max(
        0, float(Fraction(source.get("video_start_time") or "0") - Fraction(source.get("start_time") or "0"))
    ))


def frame_image(path: Path, seconds: float) -> bytes:
    """Accurately seek and decode one display-sized frame without cached files."""
    info = probe(path)
    offset = max(0, float(Fraction(info.get("video_start_time") or "0") - Fraction(info.get("start_time") or "0")))
    result = subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-threads", "2", "-filter_threads", "1",
        "-protocol_whitelist", "file,pipe", "-ss", str(seconds + offset), "-i", str(path.resolve()),
        "-map", "0:V:0", "-frames:v", "1", "-an", "-sn",
        "-vf", "scale=w='min(1920,iw)':h='min(1920,ih)':force_original_aspect_ratio=decrease",
        "-threads", "1", "-c:v", "png", "-f", "image2pipe", "pipe:1",
    ], capture_output=True, timeout=60)
    if result.returncode or not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("This frame could not be decoded. Choose an earlier time or another video.")
    return result.stdout


def validate_output(path: Path, source: dict, recipe: dict):
    info = probe(path)
    expected = preview_duration(source, recipe)
    if abs(info["duration"] - expected) > max(0.5, expected * 0.01):
        raise ValueError("Output duration differs from the source. Original preserved; result rejected.")
    if recipe["engine"] != "dlss5" and (info["width"], info["height"]) != dimensions(source, recipe):
        raise ValueError("Output size does not match the requested enhancement.")
    if recipe["engine"] == "dlss5" and (info["width"], info["height"]) != (source["width"], source["height"]):
        raise ValueError("DLSS 5 output unexpectedly changed video dimensions.")
    expected_codec = {"h264": "h264", "hevc": "hevc", "av1": "av1"}[recipe["codec"]]
    if info["codec"] != expected_codec:
        raise ValueError("Output codec differs from the selected codec.")
    if recipe.get("hdr"):
        from .hdr import validate_hdr

        validate_hdr(info)
    elif info["hdr"]:
        raise ValueError("Output unexpectedly changed SDR to HDR. Original preserved; result rejected.")
    elif not source.get("hdr"):
        from .sdr import validate_sdr

        validate_sdr(source, info)
    if recipe.get("frame_generation"):
        from .frame_generation import FPS

        try:
            actual_rate = Fraction(info["frame_rate"])
        except (ValueError, ZeroDivisionError):
            raise ValueError("Generated output has no valid frame rate.") from None
        target_rate = FPS[recipe.get("frame_rate", "60")]
        # Matroska/codec declarations can rationally approximate 1001-based
        # rates (e.g. HEVC reports 19001/317 for 60000/1001). Check the
        # actual packet clock too, rather than accepting a label alone.
        if abs(actual_rate - target_rate) > target_rate / 100_000:
            raise ValueError("Generated output frame rate differs from the requested cadence.")
        verify_packet_cadence(path, info, target_rate)
    frame_preview = recipe.get("preview_frame_time") is not None
    for key in ("audio_streams", "subtitle_streams", "attachment_streams"):
        if info[key] != (0 if frame_preview else source[key]):
            raise ValueError(f"Output lost {key.replace('_', ' ')}. Original preserved; result rejected.")
    # A frame comparison is explicitly video-only. Full exports and existing
    # audiovisual previews keep the complete preservation contract.
    if not frame_preview:
        verify_preservation(source, info, recipe)
    result = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            # Auto threading follows the host's CPU count, even when the
            # lightweight manager has a small container memory/CPU limit.
            # Bound decoder buffers for 4K validation on many-core hosts.
            "-threads",
            "2",
            "-filter_threads",
            "1",
            "-protocol_whitelist",
            "file,pipe",
            "-i",
            str(path.resolve()),
            "-t",
            "2",
            "-map",
            "0:v:0",
            "-threads",
            "1",
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


def verify_preservation(source, result, recipe):
    """Compare copied media against the picture, allowing a common mux offset."""
    # Existing persisted jobs predate this signature. Newly inspected sources
    # carry it, so both the worker and the NAS independently enforce it.
    if "preservation" not in source:
        return
    before, after = source["preservation"], result["preservation"]
    if before["attachments"] != after["attachments"] or before["title"] != after["title"]:
        raise ValueError("Output changed copied attachments or title. Original preserved; result rejected.")
    if not before["audio"] and not before["chapters"]:
        return
    try:
        shift = Fraction(result["video_start_time"]) - Fraction(source["video_start_time"])
        tolerance = Fraction(1, 1000)
        for original, returned in zip(before["audio"], after["audio"], strict=True):
            if original["codec"] != returned["codec"]:
                raise ValueError("Copied audio codec changed")
            # FFmpeg versions disagree whether stream start includes AAC
            # priming. Copied packet PTS gives both devices the same clock.
            # Persisted signatures without it retain their earlier contract.
            clock = "first_packet_time" if "first_packet_time" in original else "start_time"
            if original[clock] is not None and abs(
                Fraction(returned[clock]) - Fraction(original[clock]) - shift
            ) > tolerance:
                raise ValueError("Audio synchronization changed")
        preview = recipe["preview_seconds"]
        cut = Fraction(source["start_time"]) + preview if preview else None
        chapters = [c for c in before["chapters"] if cut is None or Fraction(c["start_time"]) < cut]
        if len(chapters) != len(after["chapters"]):
            raise ValueError("Chapter count changed")
        for original, returned in zip(chapters, after["chapters"], strict=True):
            if original["tags"] != returned["tags"]:
                raise ValueError("Chapter titles changed")
            for field in ("start_time", "end_time"):
                expected = Fraction(original[field])
                if field == "end_time" and cut is not None:
                    expected = min(expected, cut)
                if abs(Fraction(returned[field]) - expected - shift) > tolerance:
                    raise ValueError("Chapter synchronization changed")
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        raise ValueError("Output changed audio or chapter timing. Original preserved; result rejected.") from None


def verify_packet_cadence(path, info, rate):
    """Bounded packet timing sample; no decoding or reliance on nominal FPS alone."""
    start = str(Fraction(info["video_start_time"])) if info.get("video_start_time") else "0"
    # FFprobe expects decimal seek seconds, not a rational expression.
    start = str(float(Fraction(start)))
    result = subprocess.run([
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-select_streams", "V:0",
        "-read_intervals", f"{start}%+#1024", "-show_entries", "packet=pts_time", "-of", "json",
        str(path.resolve()),
    ], capture_output=True, text=True, timeout=60, check=True)
    packets = json.loads(result.stdout).get("packets", [])
    try:
        first = Fraction(packets[0]["pts_time"])
        valid = len(packets) >= 2 and all(
            abs(Fraction(packet["pts_time"]) - first - index / rate) <= Fraction(1, 1000)
            for index, packet in enumerate(packets)
        )
    except (ValueError, TypeError, KeyError, IndexError):
        valid = False
    if not valid:
        raise ValueError("Generated output packet timing differs from the requested cadence.")


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
    color_options = []
    if not info.get("hdr"):
        from .sdr import SDRColor

        color = SDRColor.read(source)
        # Lock the working pixels to RGB before the explicit final conversion.
        # This also keeps preview RGB intermediates from being treated as YUV.
        filters.append("format=rgb24")
        color_options = color.options(intermediate=recipe["codec"] == "ffv1")
        filters.append(color_options[1])
        color_options = color_options[2:]
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
        *color_options,
        "-pix_fmt", "bgr0" if recipe["codec"] == "ffv1" else "yuv420p",
        "-fps_mode", "passthrough",
        # Keep input timestamp precision instead of rounding a leading audio
        # offset to the encoder's nominal frame period (notably FFmpeg 6).
        "-enc_time_base:v", "demux",
    ]
    if recipe["preview_seconds"]:
        cmd += ["-t", str(recipe["preview_seconds"])]
    return [*cmd, "-progress", "pipe:1", "-n", str(output.resolve())]


def preserved_command(rendered, source, output, recipe, info, timing=None):
    if info.get("video_start_time") is None or info.get("start_time") is None:
        raise ValueError("Original stream offsets are unavailable; refusing to guess synchronization.")
    rendered_info = probe(rendered)
    if rendered_info.get("video_start_time") is None or rendered_info.get("start_time") is None:
        raise ValueError("Enhanced stream offsets are unavailable; refusing to guess synchronization.")
    # Enhancement engines normally reset video PTS to zero. External engines
    # may keep an offset, so align both actual timelines before copying media.
    original_offset = Fraction(info["video_start_time"]) - Fraction(info["start_time"])
    rendered_offset = Fraction(rendered_info["video_start_time"]) - Fraction(rendered_info["start_time"])
    timing_options = ["-copyts", "-start_at_zero", "-itsoffset", str(float(original_offset - rendered_offset))]
    duration_options = []
    if timing is not None:
        end = Fraction(timing["source_video_duration"]) + original_offset
        duration_options = ["-bsf:v", f"setts=duration='max(ceil(0.001/TB),min(DURATION,max(0,({end.numerator}/{end.denominator})/TB-PTS)))'"]
    command = [
        "ffmpeg", "-v", "error", "-nostdin", *timing_options, "-i", str(rendered), "-i", str(source),
        "-map", "0:V:0", "-map", "1:a?", "-map", "1:s?", "-map", "1:t?",
        "-map_metadata", "1", "-map_chapters", "1", "-c", "copy", *duration_options,
        "-metadata", "popcorn_sdr_color=",
    ]
    if recipe["preview_seconds"]:
        command += ["-t", str(recipe["preview_seconds"])]
    return [*command, "-n", str(output)]
