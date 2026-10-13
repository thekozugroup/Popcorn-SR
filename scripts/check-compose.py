"""Render every shipped topology with Docker Compose, without starting services."""

import json
import os
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    env = {key: value for key, value in os.environ.items() if not key.startswith("POPCORN_")}
    fixtures = root / "evidence" / "compose-validation"
    env.update({
        "POPCORN_ADMIN_TOKEN": "compose-validation-only-not-an-access-key",
        "POPCORN_MANAGER": "http://manager.example:8787",
        "PUID": "1000", "PGID": "1000",
        "STATE_PATH": str(fixtures / "state"),
        "LIBRARY_PATH": str(fixtures / "library"),
        "OUTPUT_PATH": str(fixtures / "output"),
        "WORKER_STATE_PATH": str(fixtures / "worker-state"),
        "SCRATCH_PATH": str(fixtures / "scratch"),
        "POPCORN_NGX_BUNDLE": str(fixtures / "sdk"),
        "POPCORN_NGX_DRIVER": str(fixtures / "driver.so"),
    })
    layouts = [("manager", ["compose.yaml"])]
    for topology, base in (
        ("paired", ["compose.worker.yaml"]),
        ("single", ["compose.yaml", "compose.single.yaml"]),
    ):
        for variant in ("cpu", "nvidia", "ai", "ngx"):
            files = base + ([] if variant == "cpu" else [f"compose.{variant}.yaml"])
            layouts.append((f"{topology}/{variant}", files))
    for name, files in layouts:
        command = ["docker", "compose", "--env-file", os.devnull, "--project-directory", str(root)]
        for file in files:
            command += ["-f", str(root / file)]
        result = subprocess.run(
            command + ["config", "--format", "json"],
            env=env, capture_output=True, text=True, check=True, timeout=30,
        )
        services = json.loads(result.stdout)["services"]
        for service in services.values():
            assert service["read_only"], f"{name}: writable container root"
            assert service["cap_drop"] == ["ALL"], f"{name}: unexpected privileges"
            temporary = service["tmpfs"]
            targets = [item.split(":", 1)[0] for item in temporary]
            assert len(set(targets)) == len(targets), f"{name}: duplicate temporary mounts"
            for mount in service["volumes"]:
                assert mount["bind"]["create_host_path"] is False, f"{name}: automatic host folders"
                if mount["target"] in {"/library", "/opt/ngx", "/opt/ngx-driver/libnvidia-ngx.so.1"}:
                    assert mount["read_only"], f"{name}: writable source/runtime"
        if name.endswith("/ngx"):
            worker = services["worker"]
            assert worker["tmpfs"] == ["/tmp:rw,exec,nosuid,nodev,size=384m"], f"{name}: NGX loading mount"
            assert "graphics" in worker["environment"]["NVIDIA_DRIVER_CAPABILITIES"], f"{name}: graphics driver"
        print(f"Compose configuration passed: {name}")


if __name__ == "__main__":
    main()
