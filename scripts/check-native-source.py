"""Compile-check Vulkan source using explicitly downloaded, pinned SDK headers.

No NVIDIA binary or header is saved in the repository or worker image.
This checks syntax only; GPU execution has separate device acceptance gates.
"""

import argparse
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

SDK_COMMIT = "374959484e79a640feaba44c93ac8cfb0a03f5b5"
VULKAN_COMMIT = "2cd90f9d20df57eac214c148f3aed885372ddcfe"
HEADERS = (
    "nvsdk_ngx_vk.h", "nvsdk_ngx_defs_vk.h", "nvsdk_ngx_defs.h", "nvsdk_ngx_params.h",
    "nvsdk_ngx_defs_dlssg.h", "nvsdk_ngx_helpers_dlssg_vk.h", "nvsdk_ngx_params_dlssg.h", "nvsdk_ngx.h",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-headers", action="store_true", required=True,
                        help="Explicitly obtain NVIDIA/Khronos headers for this temporary compile check.")
    args = parser.parse_args()
    if not args.download_headers:
        parser.error("--download-headers is required.")
    repo = Path(__file__).resolve().parents[1]
    compiler = shutil.which(os.environ.get("CXX", "g++"))
    if not compiler:
        raise RuntimeError("A C++17 compiler is required.")
    print(f"Temporarily obtaining NVIDIA SDK headers {SDK_COMMIT} and Vulkan headers {VULKAN_COMMIT}.")
    with tempfile.TemporaryDirectory(prefix="popcorn-native-check-") as temporary:
        root = Path(temporary)
        for name in HEADERS:
            url = f"https://raw.githubusercontent.com/NVIDIA/DLSS/{SDK_COMMIT}/include/{name}"
            with urllib.request.urlopen(url, timeout=30) as response:
                (root / name).write_bytes(response.read())
        url = f"https://codeload.github.com/KhronosGroup/Vulkan-Headers/tar.gz/{VULKAN_COMMIT}"
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for entry in archive:
                parts = PurePosixPath(entry.name).parts
                if len(parts) < 3 or parts[1] != "include" or not entry.isfile():
                    continue
                relative = PurePosixPath(*parts[2:])
                if ".." in relative.parts:
                    raise ValueError("Unsafe header archive path.")
                target = root / "vulkan-headers" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(entry) as content:
                    target.write_bytes(content.read())
        for source in ("ngx_vulkan_probe.cpp", "dlssg.cpp"):
            subprocess.run([
                compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fsyntax-only",
                "-DPOPCORN_VULKAN_SMOKE", "-I", str(root), "-I", str(root / "vulkan-headers"),
                str(repo / "native" / source),
            ], check=True, timeout=60)
            print(f"C++ syntax passed: {source}")
    print("Temporary headers removed. This is not a GPU render test.")


if __name__ == "__main__":
    main()
