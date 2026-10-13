"""Guard the release loader's boundary before any image is changed."""

import hashlib
import importlib.util
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_release", ROOT / "scripts/package-release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def fixture(tmp_path):
    architecture = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64"}[os.uname().machine]
    script = tmp_path / "load.sh"
    packages = {"manager": {"image": f"popcorn-sr:0.3.0-{architecture}", "rootfs_layers": ["sha256:123"]},
                "ngx": {"image": f"popcorn-sr-ngx:0.3.0-{architecture}", "rootfs_layers": ["sha256:123"]}}
    script.write_text(release.loader("0.3.0", architecture, "abc123", packages))
    (tmp_path / "payload").write_bytes(b"verified image fixture")
    (tmp_path / "SHA256SUMS").write_text(f"{hashlib.sha256((tmp_path / 'payload').read_bytes()).hexdigest()}  payload\n")
    executable = tmp_path / "docker"
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DOCKER_CALLS"\nexit 99\n')
    executable.chmod(0o755)
    environment = os.environ | {"PATH": str(tmp_path) + os.pathsep + os.environ["PATH"], "DOCKER_CALLS": str(tmp_path / "calls")}
    return script, environment


def test_corrupt_kit_stops_before_docker(tmp_path):
    script, environment = fixture(tmp_path)
    (tmp_path / "payload").write_bytes(b"tampered")
    result = subprocess.run(["sh", str(script), "all"], env=environment, capture_output=True)
    assert result.returncode != 0
    assert not (tmp_path / "calls").exists()


def test_wrong_role_stops_before_docker(tmp_path):
    script, environment = fixture(tmp_path)
    result = subprocess.run(["sh", str(script), "invalid"], env=environment, capture_output=True)
    assert result.returncode != 0
    assert not (tmp_path / "calls").exists()


def test_wrong_architecture_stops_before_docker(tmp_path):
    script, environment = fixture(tmp_path)
    executable = tmp_path / "uname"
    executable.write_text("#!/bin/sh\necho unsupported-host\n")
    executable.chmod(0o755)
    result = subprocess.run(["sh", str(script), "all"], env=environment, capture_output=True)
    assert result.returncode != 0
    assert not (tmp_path / "calls").exists()


def test_existing_different_image_is_never_replaced(tmp_path):
    script, environment = fixture(tmp_path)
    executable = tmp_path / "docker"
    executable.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$DOCKER_CALLS"\n'
                          'case "$*" in *--format*) echo another-source-commit;; esac\nexit 0\n')
    result = subprocess.run(["sh", str(script), "manager"], env=environment, capture_output=True)
    assert result.returncode != 0
    assert b"Refusing to replace" in result.stderr
    assert "load" not in (tmp_path / "calls").read_text()
