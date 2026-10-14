import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    state: Path
    library: Path
    output: Path
    admin_token: str = ""  # Legacy configuration field; no longer grants access.
    lease_seconds: int = 90
    max_upload_bytes: int = 256 * 1024**3
    reserve_bytes: int = 1024**3
    public_url: str = ""

    def __post_init__(self):
        for key in ("state", "library", "output"):
            object.__setattr__(self, key, getattr(self, key).resolve())

    @classmethod
    def from_env(cls):
        return cls(
            Path(os.environ.get("POPCORN_STATE", "/state")),
            Path(os.environ.get("POPCORN_LIBRARY", "/library")),
            Path(os.environ.get("POPCORN_OUTPUT", "/output")),
            public_url=os.environ.get("POPCORN_PUBLIC_URL", ""),
            lease_seconds=int(os.environ.get("POPCORN_LEASE_SECONDS", "90")),
            max_upload_bytes=int(os.environ.get("POPCORN_MAX_UPLOAD_GIB", "256")) * 1024**3,
            reserve_bytes=int(os.environ.get("POPCORN_RESERVE_MIB", "1024")) * 1024**2,
        )


def beneath(root: Path, relative: str, *, file: bool = False) -> Path:
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Choose a relative path inside the mounted folder.")
    root = root.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Path leaves the mounted folder.")
    if file and (not target.is_file() or target.is_symlink()):
        raise ValueError("Video no longer exists in the mounted library.")
    return target
