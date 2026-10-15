"""Pinned public FlashVSR+ assets; atomic installation without download caches."""

import argparse
import hashlib
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

RUNTIME_REVISION = "a08fb184a84cc2157c4f271234555fcda7902c87"
RUNTIME_ARCHIVE_SHA256 = "55bc3c71e80eff0e73284d1ec0703f38a0adeca64297f941747bee49e711f3d4"
MODEL_REVISION = "46b79520946ac67dec94d1566490690953c7debc"
MODEL_HASHES = {
    "turbo/dit.safetensors": "7862b92178176fa3aebc34c6c071daca6b56ab1dddb8e7ff9a01c47f5226ec8b",
    "turbo/lq_proj_in.safetensors": "e77b378ae12342eefbb58f924256f362a151b93ce73dd32808fcdaca9c051496",
    "TCDecoder.ckpt": "e224bdcf2f52745cbf4d393ff5374c2ba09e90285d5d19062d2bf63b915b6161",
}


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def download(url, target, expected):
    """A partial or incorrect download never becomes a model file."""
    if target.exists() or target.is_symlink():
        if target.is_symlink() or not target.is_file() or digest(target) != expected:
            raise ValueError(f"Existing asset differs; refusing to replace {target.name}.")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="popcorn-download-", dir=target.parent) as folder:
        temporary = Path(folder) / "asset"
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("xb") as output:
            shutil.copyfileobj(response, output, 1024 * 1024)
        if digest(temporary) != expected:
            raise ValueError("Downloaded asset checksum differs from the pinned release.")
        os.link(temporary, target)


def install_runtime(destination):
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Choose a new runtime directory; existing files are preserved.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="popcorn-runtime-", dir=destination.parent) as folder:
        work = Path(folder)
        archive = work / "runtime.tar.gz"
        download(
            f"https://codeload.github.com/OpenImagingLab/FlashVSR_Plus/tar.gz/{RUNTIME_REVISION}",
            archive, RUNTIME_ARCHIVE_SHA256,
        )
        content = work / "content"
        content.mkdir()
        prefix = f"FlashVSR_Plus-{RUNTIME_REVISION}/"
        allowed = {"inference", "model_io", "models", "operators", "prompt_tensor", "LICENSE"}
        with tarfile.open(archive) as source:
            for item in source:
                if not item.name.startswith(prefix) or not item.isfile():
                    continue
                path = Path(item.name.removeprefix(prefix))
                if path.is_absolute() or ".." in path.parts or path.parts[0] not in allowed:
                    continue
                target = content / path
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(item) as data, target.open("xb") as output:
                    shutil.copyfileobj(data, output)
        (content / ".popcorn-revision").write_text(RUNTIME_REVISION + "\n")
        # mkdir is exclusive: never merge into an unrelated concurrent directory.
        destination.mkdir()
        try:
            for child in content.iterdir():
                child.rename(destination / child.name)
        except BaseException:
            shutil.rmtree(destination)
            raise


def install_models(destination):
    # This is a deliberate persistent installation, separate from scratch jobs.
    for filename, expected in MODEL_HASHES.items():
        download(
            f"https://huggingface.co/ruchangyao/FlashVSR_plus/resolve/{MODEL_REVISION}/{filename}",
            destination / filename, expected,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("runtime", "models"))
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    (install_runtime if args.kind == "runtime" else install_models)(args.destination)


if __name__ == "__main__":
    main()
