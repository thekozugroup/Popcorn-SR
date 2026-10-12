import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    state: Path
    library: Path
    output: Path
    admin_token: str
    lease_seconds: int = 90
    max_upload_bytes: int = 256 * 1024**3
    reserve_bytes: int = 1024**3

    def __post_init__(self):
        for key in ("state", "library", "output"):
            object.__setattr__(self, key, getattr(self, key).resolve())

    @classmethod
    def from_env(cls):
        token = os.environ.get("POPCORN_ADMIN_TOKEN", "")
        token_file = os.environ.get("POPCORN_ADMIN_TOKEN_FILE")
        if token_file:
            token = Path(token_file).read_text().strip()
        if len(token) < 24:
            raise RuntimeError("Set POPCORN_ADMIN_TOKEN to a random secret of at least 24 characters.")
        return cls(
            Path(os.environ.get("POPCORN_STATE", "/state")),
            Path(os.environ.get("POPCORN_LIBRARY", "/library")),
            Path(os.environ.get("POPCORN_OUTPUT", "/output")),
            token,
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
