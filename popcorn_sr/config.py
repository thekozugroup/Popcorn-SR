import json
import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Library:
    id: str
    name: str
    path: Path

    def __post_init__(self):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", self.id) or self.id == "default":
            raise ValueError("Library IDs must be short lowercase names; default is reserved.")
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 80:
            raise ValueError("Give each library a name of 1–80 characters.")
        object.__setattr__(self, "path", self.path.resolve())


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
    library_name: str = "Your library"
    libraries: tuple[Library, ...] = ()

    def __post_init__(self):
        for key in ("state", "library", "output"):
            object.__setattr__(self, key, getattr(self, key).resolve())
        if len({item.id for item in self.libraries}) != len(self.libraries):
            raise ValueError("Library IDs must be unique.")

    def source(self, path: str, *, file: bool = False) -> Path:
        # Keep legacy job paths intact. Additional mounts use a stable namespace,
        # so changing the selected library never changes a queued job's source.
        parts = path.split("/")
        if parts[0] == "@sources":
            library = next((item for item in self.libraries if len(parts) > 1 and item.id == parts[1]), None)
            if library is None:
                raise ValueError("Library is not configured. Check its read-only mount.")
            return beneath(library.path, "/".join(parts[2:]) or ".", file=file)
        return beneath(self.library, path, file=file)

    def library_choices(self):
        return [{"id": "default", "name": self.library_name, "directory": "."}] + [
            {"id": item.id, "name": item.name, "directory": f"@sources/{item.id}"}
            for item in self.libraries
        ]

    @classmethod
    def from_env(cls):
        extra = json.loads(os.environ.get("POPCORN_EXTRA_LIBRARIES", "[]"))
        if not isinstance(extra, list) or len(extra) > 20:
            raise ValueError("POPCORN_EXTRA_LIBRARIES must be a list of up to 20 mounted libraries.")
        return cls(
            Path(os.environ.get("POPCORN_STATE", "/state")),
            Path(os.environ.get("POPCORN_LIBRARY", "/library")),
            Path(os.environ.get("POPCORN_OUTPUT", "/output")),
            public_url=os.environ.get("POPCORN_PUBLIC_URL", ""),
            lease_seconds=int(os.environ.get("POPCORN_LEASE_SECONDS", "90")),
            max_upload_bytes=int(os.environ.get("POPCORN_MAX_UPLOAD_GIB", "256")) * 1024**3,
            reserve_bytes=int(os.environ.get("POPCORN_RESERVE_MIB", "1024")) * 1024**2,
            library_name=os.environ.get("POPCORN_LIBRARY_NAME", "Your library"),
            libraries=tuple(Library(item["id"], item["name"], Path(item["path"])) for item in extra),
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
