#!/usr/bin/env python3
"""Export a committed Linux image and its identity for isolated device acceptance."""

import argparse
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--architecture", required=True, choices=["amd64", "arm64"])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    subprocess.run([
        "git", "diff", "--quiet", "HEAD", "--", "popcorn_sr", "native", "web",
        "Dockerfile", "Dockerfile.ngx", "Dockerfile.ai", "Dockerfile.restoration", "pyproject.toml", "uv.lock",
    ], check=True)
    if subprocess.check_output([
        "git", "ls-files", "--others", "--exclude-standard", "--", "popcorn_sr", "native", "web",
    ], text=True).strip():
        raise ValueError("Commit runtime source before exporting a device package.")
    inspected = json.loads(subprocess.check_output(["docker", "image", "inspect", args.image], text=True))[0]
    if inspected["Os"] != "linux" or inspected["Architecture"] != args.architecture:
        raise ValueError("Image platform does not match the requested device package.")
    if (inspected["Config"].get("Labels") or {}).get("org.opencontainers.image.revision") != commit:
        raise ValueError("Image revision must match the committed checkout.")
    for value in inspected["Config"].get("Env", []):
        if value.partition("=")[0] in {"POPCORN_ADMIN_TOKEN", "POPCORN_PAIR_CODE"}:
            raise ValueError("Device images must not contain access or pairing credentials.")
    args.output.mkdir(parents=True, exist_ok=True)
    archive, manifest = args.output / "image.tar.gz", args.output / "package.json"
    if archive.exists() or manifest.exists():
        raise FileExistsError("Device package already exists; choose a new output folder.")
    descriptor, temporary = tempfile.mkstemp(prefix=".image-", dir=args.output)
    try:
        with os.fdopen(descriptor, "wb") as destination:
            process = subprocess.Popen(["docker", "save", args.image], stdout=subprocess.PIPE)
            try:
                with gzip.GzipFile(fileobj=destination, mode="wb", compresslevel=1, mtime=0) as compressed:
                    shutil.copyfileobj(process.stdout, compressed, length=1024 * 1024)
                if process.wait() != 0:
                    raise RuntimeError("Docker image export failed.")
            finally:
                process.stdout.close()
                if process.poll() is None:
                    process.terminate()
                    process.wait()
        temporary = Path(temporary)
        with temporary.open("rb") as stream:
            archive_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        files = list(Path("popcorn_sr").glob("*.py")) + list(Path("native").glob("*.cpp")) + list(Path("native").glob("*.hpp"))
        files += [Path(name) for name in ("Dockerfile", "Dockerfile.ngx", "Dockerfile.ai", "Dockerfile.restoration", "pyproject.toml", "uv.lock")]
        data = {
            "schema": 1,
            "source_commit": commit,
            "image": args.image,
            "image_id": inspected["Id"],
            "architecture": args.architecture,
            "os": inspected["Os"],
            "rootfs_layers": inspected["RootFS"]["Layers"],
            "environment": inspected["Config"].get("Env", []),
            "archive_sha256": archive_hash,
            "archive_bytes": temporary.stat().st_size,
            "source_hashes": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)},
            "gpu_verified": False,
        }
        # Link without replacing an existing artifact, then publish its descriptor.
        os.link(temporary, archive)
        with manifest.open("x") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        print(f"Exported verified {args.architecture} image at commit {commit}.")
    finally:
        Path(temporary).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
