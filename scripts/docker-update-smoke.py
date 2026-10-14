#!/usr/bin/env python3
"""Exercise real idle replacement/rollback using explicitly staged CPU image fixtures."""

import argparse
import hashlib
import importlib.util
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
from auth_fixture import sign_in

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("host_updater", ROOT / "scripts/update-worker.py")
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def docker(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Owned Docker operation failed; command parameters are not logged.")
    return result.stdout.strip()


def wait(check, timeout=240):
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        try:
            if value := check():
                return value
        except httpx.RequestError:
            pass
        time.sleep(1)
    raise RuntimeError("Owned update acceptance timed out.")


class StagedUpdater(host.Updater):
    """Only registry staging is substituted; Docker/app/runtime checks are real."""

    def command(self, *args, **kwargs):
        if args[:2] == ("docker", "pull"):
            return "Explicit local candidate; no registry pull is claimed."
        return super().command(*args, **kwargs)

    def image(self, reference):
        if reference == self.repository + ":" + self.channel:
            image, release, revision = super().image(self.candidate)
            image["RepoDigests"] = [self.repository + "@" + image["Id"]]
            return image, release, revision
        return super().image(reference)

    def recreate(self, reference):
        staged, _, _ = super().image(self.candidate)
        if reference == self.repository + "@" + staged["Id"]:
            reference = staged["Id"]
        return super().recreate(reference)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Locally built 0.4.0 manager/CPU worker image.")
    parser.add_argument("--report", type=Path, required=True, help="New receipt under evidence/.")
    args = parser.parse_args()
    if not os.environ.get("DOCKER_HOST") and not os.environ.get("DOCKER_CONTEXT"):
        parser.error("Select an explicit isolated Docker host/context for acceptance.")
    receipt = args.report.resolve()
    if not receipt.is_relative_to(ROOT / "evidence") or receipt.exists():
        parser.error("Choose a new receipt path under evidence/.")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    source = json.loads(docker("image", "inspect", args.image))[0]
    assert source["Config"]["Labels"]["org.opencontainers.image.version"] == "0.4.0"
    identity = "popcorn-update-" + secrets.token_hex(4)
    manager, network = identity + "-manager", identity + "-network"
    baseline, bad = identity + ":baseline", identity + ":bad"
    key = secrets.token_urlsafe(40)
    created_images, created_containers = [], []
    report = {"source_commit": source["Config"]["Labels"]["org.opencontainers.image.revision"],
              "status": "running", "actual_docker_replacement": False, "actual_worker_processing": False,
              "registry_staging": "explicit local fixture; not a published release pull", "gpu_verified": False,
              "baseline": "same processing source with explicit 0.3.9 version fixture", "candidate": "unmodified 0.4.0 committed image",
              "bad_candidate": "explicit 0.4.1 version fixture with impossible scratch reserve"}

    def save():
        receipt.write_text(json.dumps(report, indent=2) + "\n")

    with tempfile.TemporaryDirectory(prefix=identity + "-", dir=ROOT / "evidence") as temporary:
        root = Path(temporary)
        for name in ("library", "output", "state", "worker-state", "scratch", "control"):
            (root / name).mkdir(mode=0o777)
            (root / name).chmod(0o777)  # Isolated bind-mount fixture, not production folder permissions.
        (root / "scratch/.popcorn-scratch").write_text(identity)
        clip = root / "library/sample.mkv"
        compose = root / "worker.yaml"
        environment = root / "worker.env"
        config = root / "update.json"
        compose.write_text(json.dumps({"services": {"worker": {
            "image": "${POPCORN_IMAGE}", "command": ["worker"], "read_only": True,
            "restart": "unless-stopped", "cpus": .5, "mem_limit": "2g", "tmpfs": ["/tmp:size=64m"],
            "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
            "labels": {"popcorn.update.acceptance": identity, "com.centurylinklabs.watchtower.enable": "false"},
            "environment": {"POPCORN_MANAGER": f"http://{manager}:8787", "POPCORN_PAIR_CODE": "${POPCORN_PAIR_CODE}",
                            "POPCORN_UPDATE_DIRECTORY": "/updates", "POPCORN_WORKER_NAME": "Actual CPU update check"},
            "volumes": [{"type": "bind", "source": str(root / name), "target": target,
                         "bind": {"create_host_path": False}} for name, target in
                        (("worker-state", "/state"), ("scratch", "/scratch"), ("control", "/updates"))],
            "healthcheck": {"disable": True}, "networks": ["acceptance"],
        }}, "networks": {"acceptance": {"external": True, "name": network}}}, indent=2))
        compose.chmod(0o600)
        host.write(config, {"role": "cpu", "project": identity, "compose": str(compose),
                            "environment": str(environment), "control": str(root / "control"),
                            "automatic": False, "validation_seconds": 18})
        try:
            for image, release, extra in ((baseline, "0.3.9", ""), (bad, "0.4.1", "ENV POPCORN_SCRATCH_RESERVE_MIB=999999999\n")):
                (root / "fixture-version").write_text(f'__version__ = "{release}"\n')
                (root / "Dockerfile").write_text(
                    f"FROM {args.image}\nUSER root\nCOPY fixture-version /tmp/fixture-version\n"
                    "RUN python -c \"import sysconfig;from pathlib import Path;v=Path('/tmp/fixture-version').read_text();"
                    "paths=[Path('/app/popcorn_sr/__init__.py'),Path(sysconfig.get_paths()['purelib'])/'popcorn_sr/__init__.py'];"
                    "assert all(p.exists() for p in paths);[p.write_text(v) for p in paths]\" && rm /tmp/fixture-version\n"
                    f"LABEL org.opencontainers.image.version=\"{release}\"\n" + extra + "USER 1000:1000\n")
                docker("build", "-t", image, str(root))
                created_images.append(image)
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=24",
                            "-f", "lavfi", "-i", "sine=frequency=440", "-t", "12", "-threads", "2", "-c:v", "libx264",
                            "-preset", "ultrafast", "-c:a", "aac", str(clip)], check=True)
            original = hashlib.sha256(clip.read_bytes()).hexdigest()
            docker("network", "create", "--label", "popcorn.update.acceptance=" + identity, network)
            docker("run", "-d", "--name", manager, "--network", network, "--read-only", "--memory", "512m", "--cpus", "1",
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp:size=64m", "-p", "127.0.0.1::8787",
                   "--label", "popcorn.update.acceptance=" + identity, "-e", "POPCORN_ADMIN_TOKEN=" + key,
                   "--mount", f"type=bind,src={root}/state,dst=/state", "--mount", f"type=bind,src={root}/library,dst=/library,readonly",
                   "--mount", f"type=bind,src={root}/output,dst=/output", args.image)
            created_containers.append(manager)
            port = docker("port", manager, "8787/tcp").rsplit(":", 1)[1]
            with httpx.Client(base_url="http://127.0.0.1:" + port, timeout=60, trust_env=False) as client:
                sign_in(client, key)
                wait(lambda: client.get("/health").is_success if docker("inspect", "--format", "{{.State.Running}}", manager) == "true" else False)
                pair = client.post("/api/pair-codes").json()["code"]
                environment.write_text(f"POPCORN_IMAGE={baseline}\nPOPCORN_PAIR_CODE={pair}\n")
                environment.chmod(0o600)
                updater = StagedUpdater(config)
                updater.candidate = args.image
                updater.command(*updater.compose, "up", "--detach", "--no-build", "--pull", "never", "worker")
                ready = wait(lambda: next((w for w in client.get("/api/state").json()["workers"]
                                           if w["capabilities"].get("initialization") == "ready"), None))
                worker_id = ready["id"]
                before = updater.container()["Id"]
                credentials_hash = hashlib.sha256((root / "worker-state/worker.json").read_bytes()).hexdigest()
                first = client.post("/api/jobs", json={"path": "sample.mkv", "worker_id": worker_id,
                                                      "recipe": {"codec": "hevc", "encoder": "cpu", "scale": 1}})
                first.raise_for_status()
                job_id = first.json()["id"]

                def job():
                    return next(j for j in client.get("/api/state").json()["jobs"] if j["id"] == job_id)

                wait(lambda: job()["status"] == "running")
                docker("exec", before, "popcorn-sr", "request-update")
                updater.run()
                assert host.read(root / "control/status.json")["state"] == "waiting"
                assert updater.container()["Id"] == before and job()["status"] == "running"
                queued = client.post("/api/jobs", json={"path": "sample.mkv", "worker_id": worker_id,
                                                       "recipe": {"codec": "h264", "encoder": "cpu", "scale": 1}})
                queued.raise_for_status()
                queued_id = queued.json()["id"]
                report["active_job_not_stopped"] = True
                save()

                def upgraded():
                    updater.run()
                    status = host.read(root / "control/status.json")
                    if status.get("state") in {"failed", "rolled_back"}:
                        raise RuntimeError("Successful candidate was not accepted.")
                    return status.get("state") == "updated"

                wait(upgraded)
                after = updater.container()["Id"]
                assert before != after
                report["actual_docker_replacement"] = True
                assert hashlib.sha256((root / "worker-state/worker.json").read_bytes()).hexdigest() == credentials_hash
                assert job()["status"] == "completed"
                report["actual_worker_processing"] = True
                download = client.get(f"/api/jobs/{job_id}/download")
                download.raise_for_status()
                assert hashlib.sha256(download.content).hexdigest() == job()["result"]["sha256"]
                report["successful_replacement"] = {"version": "0.4.0", "pairing_unchanged": True,
                                                    "active_job_download_sha256": job()["result"]["sha256"]}
                wait(lambda: next(j for j in client.get("/api/state").json()["jobs"] if j["id"] == queued_id)["status"] == "completed")
                report["queued_job_continued_after_update"] = True
                updater.candidate = bad
                wait(lambda: next(w for w in client.get("/api/state").json()["workers"] if w["id"] == worker_id)["capabilities"]["updates"]["enabled"])
                requested = client.post(f"/api/workers/{worker_id}/update")
                requested.raise_for_status()
                wait(lambda: host.read(root / "control/request.json").get("id") == requested.json()["request_id"])

                def rolled_back():
                    updater.run()
                    return host.read(root / "control/status.json").get("state") == "rolled_back"

                wait(rolled_back)
                assert updater.container()["Image"] == json.loads(docker("image", "inspect", args.image))[0]["Id"]
                assert hashlib.sha256((root / "worker-state/worker.json").read_bytes()).hexdigest() == credentials_hash
                assert not (root / "control/drain.json").exists()
                report["real_failed_startup_restored_previous_image"] = True
                assert hashlib.sha256(clip.read_bytes()).hexdigest() == original
                assert not list((root / "scratch").glob("job-*"))
                report["original_unchanged"] = report["scratch_clean"] = True
                report["status"] = "passed"
        except BaseException as exc:
            report["status"] = "failed"
            report["error"] = str(exc)
            raise
        finally:
            subprocess.run(["docker", "compose", "--project-name", identity, "--env-file", str(environment), "-f", str(compose), "down"], capture_output=True)
            for container in created_containers:
                subprocess.run(["docker", "rm", "-f", container], capture_output=True)
            subprocess.run(["docker", "network", "rm", network], capture_output=True)
            for image in created_images:
                subprocess.run(["docker", "image", "rm", image], capture_output=True)
            report["owned_resources_cleanup_attempted"] = True
            save()
    print("Actual CPU worker replacement, active-job preservation, queue continuation and rollback passed.")


if __name__ == "__main__":
    main()
