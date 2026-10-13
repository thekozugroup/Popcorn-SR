"""Adapters invoke separately installed engines; no third-party binaries are bundled."""

import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from .dlss import mode_for_recipe
from .media import dimensions, ffmpeg_command


def adapter_command(engine: str, source: Path, output: Path, recipe: dict, info: dict):
    width, height = dimensions(info, recipe)
    if engine == "realesrgan":
        return [
            os.environ.get("POPCORN_AI_PYTHON", sys.executable),
            "-m",
            "popcorn_sr.realesrgan",
            "--input",
            str(source.resolve()),
            "--output",
            str(output.resolve()),
            "--width",
            str(width),
            "--height",
            str(height),
            "--codec",
            recipe["codec"],
            "--quality",
            str(recipe["quality"]),
            "--model",
            os.environ["POPCORN_ESRGAN_MODEL"],
        ]
    custom = os.environ.get(
        {"dlss-sr": "POPCORN_DLSS_COMMAND", "dlss5": "POPCORN_DLSS5_COMMAND"}.get(engine, "")
    )
    if custom:
        template = json.loads(custom)
        if not isinstance(template, list) or not template or not all(isinstance(s, str) for s in template):
            raise ValueError("DLSS command must be a JSON argument array.")
        values = {
            "input": str(source.resolve()),
            "output": str(output.resolve()),
            "width": str(width),
            "height": str(height),
            "scale": str(recipe["scale"]),
            "codec": recipe["codec"],
            "quality": str(recipe["quality"]),
            "dlss_mode": mode_for_recipe(recipe) if engine == "dlss-sr" else "",
            "dlss_preset": recipe.get("dlss_preset", "default"),
            "temporal_quality": recipe.get("temporal_quality", "high"),
        }
        return [s.format_map(values) for s in template]
    if engine == "dlss-sr" and os.environ.get("POPCORN_NGX_LIBRARY") and os.environ.get("POPCORN_NGX_RUNTIME"):
        return [
            os.environ.get("POPCORN_NGX_PYTHON", sys.executable), "-m", "popcorn_sr.dlss_sr",
            "--input", str(source.resolve()), "--output", str(output.resolve()),
            "--width", str(width), "--height", str(height),
            "--codec", recipe["codec"], "--quality", str(recipe["quality"]),
            "--mode", mode_for_recipe(recipe), "--preset", recipe.get("dlss_preset", "default"),
            "--temporal-quality", recipe.get("temporal_quality", "high"),
            "--library", os.environ["POPCORN_NGX_LIBRARY"], "--runtime", os.environ["POPCORN_NGX_RUNTIME"],
        ]
    if engine == "rtx-vsr" and os.environ.get("POPCORN_NVIDIA_VFX") == "1":
        return [
            os.environ.get("POPCORN_AI_PYTHON", sys.executable),
            "-m",
            "popcorn_sr.nvidia_vsr",
            "--input",
            str(source.resolve()),
            "--output",
            str(output.resolve()),
            "--width",
            str(width),
            "--height",
            str(height),
            "--codec",
            recipe["codec"],
            "--quality",
            str(recipe["quality"]),
        ]
    if engine == "rtx-vsr" and os.environ.get("POPCORN_VSR_COMMAND"):
        template = json.loads(os.environ["POPCORN_VSR_COMMAND"])
        if not isinstance(template, list) or not template or not all(isinstance(s, str) for s in template):
            raise ValueError("POPCORN_VSR_COMMAND must be a JSON array of command arguments.")
        values = {
            "input": str(source.resolve()),
            "output": str(output.resolve()),
            "width": str(width),
            "height": str(height),
            "scale": str(recipe["scale"]),
            "codec": recipe["codec"],
            "quality": str(recipe["quality"]),
        }
        return [s.format_map(values) for s in template]
    fast = os.environ.get("POPCORN_FAST_RTXVSR")
    if engine == "rtx-vsr" and fast:
        return [
            fast,
            "run",
            str(source.resolve()),
            "--width",
            str(width),
            "--height",
            str(height),
            "--quality",
            "ULTRA",
            "--codec",
            recipe["codec"],
            "--out-dir",
            str(output.parent / "engine"),
        ]
    ve = os.environ.get("POPCORN_VISUAL_ENHANCER")
    if ve and platform.system() == "Windows":
        cmd = [
            ve,
            "render" if engine == "dlss5" else "upscale",
            str(source.resolve()),
            "--output",
            str(output.resolve()),
            "--codec",
            recipe["codec"],
            "--container",
            "mkv",
            "--json",
        ]
        if engine == "rtx-vsr":
            cmd += ["--engine", "rtx", "--size", f"{width}x{height}"]
        elif engine == "dlss-sr":
            cmd += [
                "--engine",
                "dlss",
                "--mode",
                {1: "dlaa", 2: "performance", 3: "ultra-performance"}[recipe["scale"]],
            ]
        return cmd
    raise ValueError("This enhancement engine is not configured on this worker.")


def engine_result(engine: str, output: Path):
    if (
        engine == "rtx-vsr"
        and os.environ.get("POPCORN_FAST_RTXVSR")
        and not os.environ.get("POPCORN_VSR_COMMAND")
        and os.environ.get("POPCORN_NVIDIA_VFX") != "1"
    ):
        candidates = list((output.parent / "engine").glob("*_vsr.mp4"))
        if len(candidates) != 1:
            raise ValueError("RTX engine did not produce exactly one finished video.")
        return candidates[0]
    return output


def processing_command(source: Path, output: Path, recipe: dict, info: dict):
    if recipe["engine"] == "resize":
        return ffmpeg_command(source, output, recipe, info)
    return adapter_command(recipe["engine"], source, output, recipe, info)


def run_check(command, *, timeout=60, scratch=None, stopped=None):
    try:
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("POPCORN_ADMIN") or key in {"POPCORN_PAIR_CODE", "POPCORN_ACTIVE_JOB_FD"}:
                env.pop(key, None)
        if scratch is not None:
            env.update(
                {
                    "TMPDIR": str(scratch),
                    "TEMP": str(scratch),
                    "TMP": str(scratch),
                    "XDG_CACHE_HOME": str(scratch.parent / "cache"),
                    "CUDA_CACHE_PATH": str(scratch.parent / "cache" / "cuda"),
                }
            )
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            start_new_session=os.name == "posix",
        )
        try:
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if time.monotonic() >= deadline or (stopped is not None and stopped.is_set()):
                    return False
                time.sleep(0.1)
            return process.returncode == 0
        finally:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            elif process.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10
                )
                process.wait()
    except (OSError, subprocess.TimeoutExpired):
        return False


def detect_capabilities(scratch: Path, stopped=None):
    """Require an actual encode, and an actual AI render, before advertising support."""
    from .media import probe
    from .models import Recipe

    encoders, engines, notes = [], ["resize"], {}
    gpu = "CPU worker"
    if shutil.which("nvidia-smi"):
        try:
            gpu = (
                subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                .stdout.strip()
                .splitlines()[0]
            )
        except (OSError, subprocess.TimeoutExpired, IndexError):
            pass
    for name, encoder in {
        "h264_cpu": "libx264",
        "hevc_cpu": "libx265",
        "av1_cpu": "libsvtav1",
        "h264_nvidia": "h264_nvenc",
        "hevc_nvidia": "hevc_nvenc",
        "av1_nvidia": "av1_nvenc",
    }.items():
        if stopped is not None and stopped.is_set():
            raise ValueError("Worker initialization stopped.")
        target = scratch / f"check-{name}.mkv"
        command = [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=256x144:rate=24",
            "-frames:v",
            "2",
            "-c:v",
            encoder,
            "-threads",
            "2",
            "-y",
            str(target),
        ]
        if run_check(command, scratch=scratch, stopped=stopped):
            encoders.append(name)
        target.unlink(missing_ok=True)
    configured = {}
    if os.environ.get("POPCORN_ESRGAN_MODEL"):
        configured["realesrgan"] = True
    if os.environ.get("POPCORN_DLSS_COMMAND") or (
        os.environ.get("POPCORN_NGX_LIBRARY") and os.environ.get("POPCORN_NGX_RUNTIME")
    ):
        configured["dlss-sr"] = True
    if os.environ.get("POPCORN_DLSS5_COMMAND"):
        configured["dlss5"] = True
    if (
        os.environ.get("POPCORN_FAST_RTXVSR")
        or os.environ.get("POPCORN_VSR_COMMAND")
        or os.environ.get("POPCORN_NVIDIA_VFX") == "1"
    ):
        configured["rtx-vsr"] = True
    if os.environ.get("POPCORN_VISUAL_ENHANCER") and platform.system() == "Windows":
        configured.update({"rtx-vsr": True, "dlss-sr": True, "dlss5": True})
    dlss_settings = {}
    for engine in configured:
        if stopped is not None and stopped.is_set():
            raise ValueError("Worker initialization stopped.")
        folder = scratch / f"check-{engine}"
        folder.mkdir(exist_ok=True)
        source, output = folder / "input.mkv", folder / "result.mkv"
        try:
            if "h264_nvidia" not in encoders:
                raise ValueError("NVIDIA H.264 encoding failed its hardware check.")
            if not run_check(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=256x144:rate=24",
                    "-t",
                    "1",
                    "-c:v",
                    "libx264",
                    "-y",
                    str(source),
                ],
                scratch=scratch,
                stopped=stopped,
            ):
                raise ValueError("Could not prepare an engine test clip.")
            recipe = Recipe(engine=engine, encoder="nvidia", scale=1 if engine == "dlss5" else 2).model_dump()
            info = probe(source)
            if not run_check(
                adapter_command(engine, source, output, recipe, info),
                timeout=180,
                scratch=scratch,
                stopped=stopped,
            ):
                raise ValueError("Engine processing check failed. Verify runtime, driver and hardware.")
            processed = engine_result(engine, output)
            result = probe(processed)
            expected = (256, 144) if engine == "dlss5" else dimensions(info, recipe)
            if (result["width"], result["height"]) != expected or abs(result["duration"] - 1) > 0.5:
                raise ValueError("Engine test produced unexpected dimensions or duration.")
            if not run_check(
                ["ffmpeg", "-v", "error", "-i", str(processed), "-f", "null", "-"],
                scratch=scratch,
                stopped=stopped,
            ):
                raise ValueError("Engine test output failed decoding.")
            engines.append(engine)
            if engine == "dlss-sr" and os.environ.get("POPCORN_NGX_LIBRARY") and not os.environ.get("POPCORN_DLSS_COMMAND"):
                report = folder / "settings.json"
                if run_check(
                    adapter_command(engine, source, output, recipe, info) + ["--verify-settings", str(report)],
                    timeout=420, scratch=scratch, stopped=stopped,
                ):
                    dlss_settings = json.loads(report.read_text())
                else:
                    notes[engine] = "Default DLSS works; advanced settings failed verification."
        except (ValueError, OSError, KeyError) as exc:
            notes[engine] = str(exc)
        finally:
            shutil.rmtree(folder)
    return {
        "engines": engines,
        "encoders": encoders,
        "device": gpu,
        "platform": platform.system(),
        "architecture": platform.machine(),
        "notes": notes,
        "dlss_sr": dlss_settings,
    }
