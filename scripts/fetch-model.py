#!/usr/bin/env python3
"""Download the official model once to the selected scratch drive, verify it, then publish."""

import argparse
import hashlib
import urllib.request
from pathlib import Path

URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
SHA256 = "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"
parser = argparse.ArgumentParser()
parser.add_argument("scratch", type=Path)
args = parser.parse_args()
if not (args.scratch / ".popcorn-scratch").is_file():
    parser.error("Initialize and mount this scratch drive first.")
folder = args.scratch / "models"
folder.mkdir(exist_ok=True)
final = folder / "RealESRGAN_x4plus.pth"
if final.exists():
    parser.exit(0, f"Model already exists: {final}. It will be verified before use.\n")
temporary = folder / "RealESRGAN_x4plus.pth.partial"
digest = hashlib.sha256()
try:
    with urllib.request.urlopen(URL, timeout=60) as response, temporary.open("wb") as out:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            out.write(chunk)
    if digest.hexdigest() != SHA256:
        raise RuntimeError("Model checksum mismatch. Download rejected.")
    temporary.rename(final)
    print(f"Verified model saved to {final}")
finally:
    temporary.unlink(missing_ok=True)
