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
        "POPCORN_MANAGER": "http://manager.example:8787",
        "PUID": "1000", "PGID": "1000",
        "STATE_PATH": str(fixtures / "state"),
        "LIBRARY_PATH": str(fixtures / "library"),
        "OUTPUT_PATH": str(fixtures / "output"),
        "WORKER_STATE_PATH": str(fixtures / "worker-state"),
        "SCRATCH_PATH": str(fixtures / "scratch"),
        "POPCORN_NGX_BUNDLE": str(fixtures / "sdk"),
        "POPCORN_NGX_DRIVER": str(fixtures / "driver.so"),
        "UPDATE_CONTROL_PATH": str(fixtures / "updates"),
        "MOVIES_PATH": str(fixtures / "movies"),
        "TV_PATH": str(fixtures / "shows"),
        "RESTORATION_MODELS_PATH": str(fixtures / "models"),
    })
    layouts = [("manager", ["compose.yaml"])]
    layouts.append(("manager/library", ["compose.yaml", "compose.library.yaml"]))
    layouts.append(("spark", ["compose.spark.yaml"]))
    layouts.append(("spark/updates", ["compose.spark.yaml", "compose.updates.yaml"]))
    for topology, base in (
        ("paired", ["compose.worker.yaml"]),
        ("single", ["compose.yaml", "compose.single.yaml"]),
    ):
        for variant in ("cpu", "nvidia", "ai", "ngx", "restoration"):
            files = base + ([] if variant == "cpu" else [f"compose.{variant}.yaml"])
            layouts.append((f"{topology}/{variant}", files))
            layouts.append((f"{topology}/{variant}/updates", files + ["compose.updates.yaml"]))
    for name, files in layouts:
        command = ["docker", "compose", "--env-file", os.devnull, "--project-directory", str(root)]
        for file in files:
            command += ["-f", str(root / file)]
        result = subprocess.run(
            command + ["config", "--format", "json"],
            env=env, capture_output=True, text=True, check=True, timeout=30,
        )
        services = json.loads(result.stdout)["services"]
        if name.startswith("spark"):
            assert set(services) == {"worker"}, f"{name}: unexpected sidecar"
            worker = services["worker"]
            assert "build" not in worker, f"{name}: host build required"
            assert not worker.get("ports"), f"{name}: inbound worker port"
            assert int(worker["mem_limit"]) == int(worker["memswap_limit"]) == 32 * 1024**3
            assert worker["logging"]["driver"] == "none"
            assert worker["labels"]["com.centurylinklabs.watchtower.enable"] == "false"
            models = next(m for m in worker["volumes"] if m["target"] == "/models/flashvsr")
            assert not models.get("read_only", False), f"{name}: built-in model install blocked"
        for service in services.values():
            assert service["read_only"], f"{name}: writable container root"
            assert service["cap_drop"] == ["ALL"], f"{name}: unexpected privileges"
            temporary = service["tmpfs"]
            targets = [item.split(":", 1)[0] for item in temporary]
            assert len(set(targets)) == len(targets), f"{name}: duplicate temporary mounts"
            for mount in service["volumes"]:
                # Compose 2 omits false fields; Compose 5 emits them explicitly.
                assert not mount.get("bind", {}).get("create_host_path", False), f"{name}: automatic host folders"
                if mount["target"] in {"/library", "/opt/ngx", "/opt/ngx-driver/libnvidia-ngx.so.1"} or mount["target"].startswith("/sources/"):
                    assert mount["read_only"], f"{name}: writable source/runtime"
        if "/ngx" in name:
            worker = services["worker"]
            assert worker["tmpfs"] == ["/tmp:rw,exec,nosuid,nodev,size=384m"], f"{name}: NGX loading mount"
            assert "graphics" in worker["environment"]["NVIDIA_DRIVER_CAPABILITIES"], f"{name}: graphics driver"
        if name.endswith("/updates"):
            worker = services["worker"]
            assert worker["environment"]["POPCORN_UPDATE_DIRECTORY"] == "/updates"
            assert worker["labels"]["com.centurylinklabs.watchtower.enable"] == "false"
            assert all(mount["source"] != "/var/run/docker.sock" for mount in worker["volumes"])
        print(f"Compose configuration passed: {name}")


if __name__ == "__main__":
    main()
