#!/usr/bin/env python3
"""Prove a real paired-container roundtrip without touching the operator's library."""

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--image", default="popcorn-sr:dev")
parser.add_argument("--report", type=Path, default=Path("evidence/docker-smoke.json"))
args = parser.parse_args()
identity = "popcorn-check-" + secrets.token_hex(4)
network, manager, worker = identity, identity + "-manager", identity + "-worker"
key = secrets.token_urlsafe(32)


def docker(*arguments):
    result = subprocess.run(["docker", *arguments], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-1000:])
    return result.stdout.strip()


Path("evidence").mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="popcorn-smoke-", dir=Path("evidence").resolve()) as temp:
    root = Path(temp)
    for name in ("library", "output", "manager-state", "worker-state", "scratch"):
        (root / name).mkdir(mode=0o777)
        (root / name).chmod(0o777)
    (root / "scratch" / ".popcorn-scratch").write_text(identity)
    clip = root / "library" / "sample.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x96:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(clip),
        ],
        check=True,
    )
    original = hashlib.sha256(clip.read_bytes()).hexdigest()
    environment = root / "manager.env"
    environment.write_text(f"POPCORN_ADMIN_TOKEN={key}\nPOPCORN_RESERVE_MIB=0\n")
    environment.chmod(0o600)
    try:
        docker("network", "create", network)
        docker(
            "run",
            "-d",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--name",
            manager,
            "--network",
            network,
            "--network-alias",
            "manager",
            "-p",
            "127.0.0.1::8787",
            "--env-file",
            str(environment),
            "--read-only",
            "--tmpfs",
            "/tmp:size=64m",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "-v",
            f"{root / 'manager-state'}:/state",
            "-v",
            f"{root / 'library'}:/library:ro",
            "-v",
            f"{root / 'output'}:/output",
            args.image,
        )
        mapped = docker("port", manager, "8787/tcp").splitlines()[0]
        address = "http://" + mapped
        with httpx.Client(base_url=address, headers={"Authorization": f"Bearer {key}"}, timeout=20) as client:
            for _ in range(60):
                try:
                    if client.get("/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Manager did not start: " + docker("logs", manager)[-1200:])
            page = client.get("/")
            page.raise_for_status()
            assets = re.findall(r'(?:src|href)="(/assets/bundles/[^" ]+)"', page.text)
            if len(assets) < 2:
                raise RuntimeError("Built Web UI assets are missing from the image.")
            for asset in assets:
                client.get(asset).raise_for_status()
            policy = client.get("/assets/ui-policy.json").json()
            if not all(value in page.headers["Content-Security-Policy"] for value in policy["style_hashes"]):
                raise RuntimeError("Web UI stylesheet policy is missing from the image.")
            code = client.post("/api/pair-codes").json()["code"]
            worker_env = root / "worker.env"
            worker_env.write_text(
                f"POPCORN_MANAGER=http://manager:8787\nPOPCORN_PAIR_CODE={code}\nPOPCORN_WORKER_NAME=Container verification\nPOPCORN_SCRATCH_RESERVE_MIB=0\n"
            )
            worker_env.chmod(0o600)
            docker(
                "run",
                "-d",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--name",
                worker,
                "--network",
                network,
                "--env-file",
                str(worker_env),
                "--read-only",
                "--tmpfs",
                "/tmp:size=64m",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--no-healthcheck",
                "-v",
                f"{root / 'worker-state'}:/state",
                "-v",
                f"{root / 'scratch'}:/scratch",
                args.image,
                "worker",
            )
            for _ in range(120):
                state = client.get("/api/state").json()
                if state["workers"]:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Worker did not pair: " + docker("logs", worker)[-500:])
            response = client.post(
                "/api/jobs",
                json={
                    "path": "sample.mkv",
                    "recipe": {"scale": 2, "denoise": True, "output_directory": "verified"},
                },
            )
            response.raise_for_status()
            identity = response.json()["id"]
            for _ in range(120):
                jobs = client.get("/api/state").json()["jobs"]
                job = next(j for j in jobs if j["id"] == identity)
                if job["status"] in {"completed", "failed"}:
                    break
                time.sleep(1)
            assert job["status"] == "completed", job
            assert hashlib.sha256(clip.read_bytes()).hexdigest() == original
            output = root / "output" / job["result"]["path"]
            assert output.is_file()
            assert (
                hashlib.sha256(client.get(f"/api/jobs/{identity}/download").content).hexdigest()
                == job["result"]["sha256"]
            )
            assert not list((root / "scratch").glob("job-*"))
            report = {
                "status": "passed",
                "image": args.image,
                "image_id": docker("image", "inspect", "--format", "{{.Id}}", args.image),
                "architecture": docker("image", "inspect", "--format", "{{.Architecture}}", args.image),
                "worker_capabilities": state["workers"][0]["capabilities"],
                "result": job["result"],
                "original_unchanged": True,
                "scratch_cleaned": True,
            }
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n")
            print(
                f"Paired Docker roundtrip passed. {report['architecture']}, {job['result']['width']}×{job['result']['height']}, audio preserved, checksums verified."
            )
    finally:
        for container in (worker, manager):
            subprocess.run(["docker", "rm", "-f", container], capture_output=True)
        subprocess.run(["docker", "network", "rm", network], capture_output=True)
