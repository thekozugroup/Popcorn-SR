"""Bind scratch identity to its filesystem, including across worker restarts."""

import json
import os
import secrets
from pathlib import Path


def atomic_private_json(path: Path, data: dict):
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def filesystem_id(path: Path) -> str:
    if hasattr(os, "statvfs"):
        identity = getattr(os.statvfs(path), "f_fsid", None)
        if identity is not None:
            return f"fs:{identity:x}"
    return f"device:{path.stat().st_dev}"


def read_marker(path: Path) -> dict:
    marker = path / ".popcorn-scratch"
    if marker.is_symlink() or not marker.is_file() or marker.stat().st_size > 4096:
        raise ValueError("Scratch drive is not ready. Mount the drive and run init-scratch on that path.")
    text = marker.read_text().strip()
    if not text:
        raise ValueError("Scratch drive marker is empty. Initialize the intended drive again.")
    actual = filesystem_id(path)
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Scratch drive marker is damaged. Verify the drive before reinitializing."
            ) from exc
        if (
            not isinstance(data, dict)
            or data.get("version") != 1
            or not isinstance(data.get("drive_id"), str)
            or not data["drive_id"]
        ):
            raise ValueError("Scratch drive marker is not supported.")
        if data.get("filesystem_id") != actual:
            raise ValueError(
                "Scratch filesystem changed. Mount the original drive; a copied marker is insufficient."
            )
        return data
    # Retain compatibility with older markers; the worker's private state pins
    # the observed filesystem before any processing is allowed.
    return {"version": 1, "drive_id": text, "filesystem_id": actual}


def initialize(path: Path):
    path = path.resolve()
    if not path.is_dir():
        raise ValueError("Scratch folder must already exist. Mount the intended drive first.")
    marker = path / ".popcorn-scratch"
    if marker.exists() or marker.is_symlink():
        data = read_marker(path)
    else:
        data = {"version": 1, "drive_id": secrets.token_hex(16), "filesystem_id": filesystem_id(path)}
    atomic_private_json(marker, data)
    return data
