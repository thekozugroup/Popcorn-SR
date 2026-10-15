import os
import stat
from pathlib import Path

from .media import output_suffix


def remove_preview(output: Path, job: dict):
    """Unlink only this job's generated preview, without following any symlinks."""
    result = job.get("result")
    if not result:
        if job["status"] == "completed":
            raise ValueError("This preview has no saved result. Check its output folder.")
        return
    suffix = output_suffix(job.get("source", {}), job["recipe"])
    name = f"{Path(job['path']).stem[:140]}.preview.{job['id']}{suffix}"
    relative = Path(job["recipe"]["output_directory"]) / name
    if relative.is_absolute() or ".." in relative.parts or result["path"] != relative.as_posix():
        raise ValueError("Preview path does not match this job. No files were removed.")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        folder = os.open(output, flags)
    except OSError as exc:
        raise ValueError("Output folder is unavailable. Reconnect it before deleting the preview.") from exc
    try:
        for part in relative.parts[:-1]:
            try:
                child = os.open(part, flags, dir_fd=folder)
            except FileNotFoundError:
                return  # Already removed outside the app; clear the stale entry.
            os.close(folder)
            folder = child
        try:
            saved = os.stat(name, dir_fd=folder, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not stat.S_ISREG(saved.st_mode):
            raise ValueError("Preview is no longer a regular file. No files were removed.")
        os.unlink(name, dir_fd=folder)
    except OSError as exc:
        raise ValueError("Could not delete this preview. Check its output folder and permissions.") from exc
    finally:
        os.close(folder)
