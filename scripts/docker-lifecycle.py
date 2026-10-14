#!/usr/bin/env python3
"""Execute the shipped CPU Compose layouts and safe restart/drive-loss recovery."""

import argparse
import datetime
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

import httpx
from auth_fixture import sign_in

REPO = Path(__file__).resolve().parents[1]


def run(*command, env=None, check=True, timeout=180):
    result = subprocess.run(command, cwd=REPO, env=env, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        # Compose diagnostics can include environment interpolation. Do not print secrets.
        raise RuntimeError(f"{command[0]} {command[1]} failed (exit {result.returncode}).")
    return result


def wait_for(description, callback, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = callback()
        if result:
            return result
        time.sleep(0.5)
    raise RuntimeError(f"Timed out: {description}.")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class Layout:
    def __init__(self, root, image, mode, report):
        self.root, self.image, self.mode, self.report = root, image, mode, report
        self.project = "popcorn-lifecycle-" + secrets.token_hex(6)
        self.worker_project = self.project if mode == "single" else self.project + "-worker"
        self.key = secrets.token_urlsafe(32)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("POPCORN_", "COMPOSE_"))}
        self.env.update({
            "PUID": str(os.getuid()), "PGID": str(os.getgid()),
            "STATE_PATH": str(root / "manager-state"), "LIBRARY_PATH": str(root / "library"),
            "OUTPUT_PATH": str(root / "output"), "WORKER_STATE_PATH": str(root / "worker-state"),
            "SCRATCH_PATH": str(root / "scratch"), "POPCORN_ADMIN_TOKEN": self.key,
            "POPCORN_PAIR_CODE": "", "POPCORN_MANAGER": "http://manager:8787",
            "POPCORN_WORKER_NAME": "Compose lifecycle verification",
        })
        self.client = None
        self.override = root / "override.yaml"
        self.worker_override = root / "worker-override.yaml"
        self.override.write_text(f"""services:
  manager:
    image: {json.dumps(image)}
    pull_policy: never
    ports: !override ["127.0.0.1::8787"]
    cpus: 0.5
    mem_limit: 512m
    environment:
      POPCORN_RESERVE_MIB: "0"
      POPCORN_LEASE_SECONDS: "16"
""" + (self.worker_yaml() if mode == "single" else ""))
        if mode == "paired":
            self.worker_override.write_text(
                "services:\n" + self.worker_yaml() + f"""networks:
  default:
    external: true
    name: {self.project}_default
""")

    def worker_yaml(self):
        return f"""  worker:
    image: {json.dumps(self.image)}
    pull_policy: never
    cpus: 2
    mem_limit: 2g
    environment:
      POPCORN_SCRATCH_RESERVE_MIB: "0"
"""

    def compose(self, *arguments, worker=False, check=True):
        files = ["compose.yaml"]
        project, override = self.project, self.override
        if self.mode == "single":
            files.append("compose.single.yaml")
        elif worker:
            files = ["compose.worker.yaml"]
            project, override = self.worker_project, self.worker_override
        command = ["docker", "compose", "--env-file", "/dev/null", "--project-directory", str(REPO),
                   "-p", project]
        for file in [*files, str(override)]:
            command += ["-f", file]
        return run(*command, *arguments, env=self.env, check=check)

    def container(self, service):
        return self.compose("ps", "-aq", service, worker=service == "worker").stdout.strip()

    def api(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def state(self):
        return self.api("GET", "/api/state")

    def record(self, name, **details):
        self.report["checks"].append({"layout": self.mode, "name": name, "status": "passed", **details})
        print(f"{self.mode}: {name} passed", flush=True)

    def ready(self, after=0):
        def current():
            workers = self.state()["workers"]
            return next((w for w in workers if not w["revoked"] and w["last_seen"] > after
                         and w["capabilities"].get("initialization") == "ready"), None)
        return wait_for("worker ready", current)

    def recreate(self):
        timestamp = time.time()
        self.compose("up", "-d", "--no-build", "--force-recreate", "worker", worker=True)
        worker = self.ready(timestamp)
        if worker["id"] != self.worker_id or sha(self.root / "worker-state" / "worker.json") != self.credentials:
            raise RuntimeError("Restart changed the saved worker identity.")
        if json.loads((self.root / "scratch" / ".popcorn-scratch").read_text()) != self.marker:
            raise RuntimeError("Restart changed the temporary drive identity.")
        return worker

    def start(self):
        self.compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "120", "manager")
        self.connect_client()
        code = self.api("POST", "/api/pair-codes")["code"]
        self.env["POPCORN_PAIR_CODE"] = code
        self.compose("run", "--rm", "--no-deps", "worker", "init-scratch", "/scratch", worker=True)
        self.marker = json.loads((self.root / "scratch" / ".popcorn-scratch").read_text())
        self.compose("up", "-d", "--no-build", "worker", worker=True)
        worker = self.ready()
        self.worker_id = worker["id"]
        self.credentials = sha(self.root / "worker-state" / "worker.json")
        # The consumed code must not be reusable; the worker's private credential is sufficient.
        reused = self.client.post("/api/workers/pair", json={
            "code": code, "name": "Reuse must fail", "capabilities": {}, "scratch": {},
        })
        if reused.status_code != 400:
            raise RuntimeError("Pairing code was reusable.")
        self.env["POPCORN_PAIR_CODE"] = ""
        self.recreate()
        for service in ("manager", "worker"):
            info = json.loads(run("docker", "inspect", self.container(service)).stdout)[0]
            config = info["HostConfig"]
            if not config["ReadonlyRootfs"] or "ALL" not in config["CapDrop"]:
                raise RuntimeError("Compose security settings were lost.")
            if "no-new-privileges:true" not in config["SecurityOpt"]:
                raise RuntimeError("Compose privilege restriction was lost.")
            if config["RestartPolicy"]["Name"] != "unless-stopped":
                raise RuntimeError("Compose restart policy was lost.")
            if service == "manager" and any(m["RW"] for m in info["Mounts"] if m["Destination"] == "/library"):
                raise RuntimeError("Library was mounted writable.")
        self.record("one-use pairing, saved identity and shipped security")

    def connect_client(self):
        # Docker can reallocate the test's ephemeral loopback port after restart.
        if self.client:
            self.client.close()
        port = self.compose("port", "manager", "8787").stdout.strip()
        self.client = httpx.Client(base_url="http://" + port,
                                  timeout=20)
        sign_in(self.client, self.key)

    def job(self, identity):
        return next(j for j in self.state()["jobs"] if j["id"] == identity)

    def submit(self, long=False):
        return self.api("POST", "/api/jobs", json={
            "path": "long.mkv" if long else "sample.mkv", "worker_id": self.worker_id,
            "recipe": {"scale": 4 if long else 2, "denoise": True, "sharpen": long,
                       "output_directory": "verified"},
        })["id"]

    def active(self):
        identity = self.submit(long=True)

        def processing():
            job = self.job(identity)
            if job["status"] in {"completed", "failed", "cancelled"}:
                raise RuntimeError("Fault fixture finished before the fault could be injected.")
            top = run("docker", "top", self.container("worker"), "-eo", "pid,args", check=False).stdout
            return job["status"] == "running" and job["progress"] > 10 and "ffmpeg" in top

        wait_for("active encoder and reported progress", processing)
        folders = list((self.root / "scratch").glob(f"job-{identity}-*"))
        if len(folders) != 1 or not (folders[0] / ".popcorn-job.json").is_file():
            raise RuntimeError("Active job ownership marker missing.")
        return identity, folders[0]

    def terminal(self, identity, expected="failed"):
        job = wait_for("job terminal", lambda: (j if (j := self.job(identity))["status"]
                                                in {"completed", "failed", "cancelled"} else None))
        if job["status"] != expected or job["result"] is not None:
            raise RuntimeError("Interrupted job published a result or reached the wrong state.")
        if any((self.root / "output").rglob(f"*{identity}*")):
            raise RuntimeError("Interrupted job left a published or partial returned copy.")
        return job

    def delivered(self):
        identity = self.submit()
        job = wait_for("delivered copy", lambda: (j if (j := self.job(identity))["status"]
                                                  in {"completed", "failed"} else None))
        if job["status"] != "completed":
            raise RuntimeError("Generated video did not complete: " + str(job.get("error")))
        output = self.root / "output" / job["result"]["path"]
        download = self.client.get(f"/api/jobs/{identity}/download")
        download.raise_for_status()
        if sha(output) != job["result"]["sha256"] or hashlib.sha256(download.content).hexdigest() != sha(output):
            raise RuntimeError("Returned copy checksum mismatch.")
        run("ffmpeg", "-v", "error", "-xerror", "-i", str(output), "-f", "null", "-")
        if job["result"]["width"] != 320 or job["result"]["height"] != 192:
            raise RuntimeError("Unexpected returned dimensions.")
        self.record("generated video and authenticated return", job_id=identity,
                    result_sha256=sha(output), width=320, height=192)
        return identity

    def recovery(self):
        unrelated = self.root / "scratch" / "job-unrelated"
        unrelated.mkdir()
        (unrelated / "keep").write_text("not owned by the worker\n")
        identity, folder = self.active()
        started = time.monotonic()
        self.compose("stop", "-t", "15", "worker", worker=True)
        self.terminal(identity)
        if folder.exists():
            raise RuntimeError("Graceful stop left owned scratch files.")
        self.record("active graceful shutdown", seconds=round(time.monotonic() - started, 2))
        self.recreate()

        identity, folder = self.active()
        container = self.container("worker")
        # Prevent automatic recovery until the crash residue has been inspected.
        run("docker", "update", "--restart=no", container)
        run("docker", "kill", "--signal=KILL", container)
        wait_for("hard crash exited", lambda: run("docker", "inspect", "--format", "{{.State.Running}}",
                                                  container).stdout.strip() == "false")
        if not folder.is_dir():
            raise RuntimeError("Hard crash did not leave the expected owned recovery fixture.")
        self.recreate()  # Actual Compose restores its declared restart policy.
        self.terminal(identity)
        wait_for("crash scratch recovery", lambda: not folder.exists())
        if run("docker", "inspect", "--format", "{{.HostConfig.RestartPolicy.Name}}",
               self.container("worker")).stdout.strip() != "unless-stopped":
            raise RuntimeError("Compose did not restore the restart policy.")
        self.record("active hard crash and owned-only recovery", automatic_restart_paused_for_injection=True)

        identity, folder = self.active()
        marker = self.root / "scratch" / ".popcorn-scratch"
        saved = marker.read_bytes()
        try:
            marker.unlink()
            started = time.monotonic()
            self.terminal(identity)
            wait_for("encoder stopped after drive loss", lambda: "ffmpeg" not in run(
                "docker", "top", self.container("worker"), "-eo", "pid,args", check=False).stdout)
            if not folder.is_dir():
                raise RuntimeError("Worker removed files through an unavailable drive.")
            self.record("active missing-marker stop", seconds=round(time.monotonic() - started, 2),
                        files_preserved_until_original_drive_returned=True)
        finally:
            marker.write_bytes(saved)
        self.recreate()
        wait_for("restored drive recovery", lambda: not folder.exists())

        self.compose("stop", "-t", "15", "worker", worker=True)
        scratch, absent = self.root / "scratch", self.root / "scratch-absent"
        scratch.rename(absent)
        try:
            refused = self.compose("up", "-d", "--no-build", "--force-recreate", "worker",
                                   worker=True, check=False)
            if refused.returncode == 0 or scratch.exists():
                raise RuntimeError("Compose created or accepted a missing temporary-drive folder.")
        finally:
            absent.rename(scratch)
        self.recreate()
        self.record("missing host folder refused without recreation")

        copied = run("docker", "run", "--rm", "--name", self.project + "-copied-drive",
                     "--label", "com.docker.compose.project=" + self.project,
                     "--network", "none", "--read-only", "--cap-drop=ALL", "--cpus", "0.5", "--memory", "128m",
                     "--security-opt=no-new-privileges:true", "--user", f"{os.getuid()}:{os.getgid()}",
                     "--tmpfs", "/scratch:size=8m,mode=1777", "--tmpfs", "/state:size=8m,mode=1777",
                     "--mount", f"type=bind,src={marker},dst=/scratch/.popcorn-scratch,readonly",
                     self.image, "worker", check=False)
        if copied.returncode != 1 or "copied marker is insufficient" not in copied.stderr:
            raise RuntimeError("A copied marker on a different real filesystem was not refused.")
        self.record("copied marker on actual tmpfs refused")
        if (unrelated / "keep").read_text() != "not owned by the worker\n":
            raise RuntimeError("Recovery altered an unrelated folder.")
        if any(p.name != "job-unrelated" for p in scratch.glob("job-*")):
            raise RuntimeError("Owned job files remain after recovery.")
        self.record("unrelated scratch folder preserved")

    def verify(self):
        self.start()
        completed = self.delivered()
        # Restart the manager while idle; persistent jobs and pairing must survive.
        self.compose("restart", "manager")
        self.compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "120", "manager")
        self.connect_client()
        if self.job(completed)["status"] != "completed" or self.ready()["id"] != self.worker_id:
            raise RuntimeError("Manager restart lost persistent state.")
        self.record("manager restart retains jobs and pairing")
        if self.mode == "single":
            self.recovery()
        self.delivered()
        self.compose("stop", "-t", "15", "worker", worker=True)
        self.api("POST", f"/api/workers/{self.worker_id}/revoke")
        # A one-off start avoids an intentional restart loop after revocation.
        revoked = self.compose("run", "--rm", "--no-deps", "worker", worker=True, check=False)
        if revoked.returncode != 1 or "revoked" not in revoked.stderr.lower():
            raise RuntimeError("Saved revoked credentials were not refused.")
        if len(self.state()["workers"]) != 1:
            raise RuntimeError("Revocation unexpectedly paired another worker.")
        self.record("revoked saved credentials refused")

    def close(self):
        if self.client:
            self.client.close()
        run("docker", "rm", "-f", self.project + "-copied-drive", check=False)
        if self.mode == "paired":
            self.compose("down", "--remove-orphans", worker=True)
        self.compose("down", "--remove-orphans")
        for project in {self.project, self.worker_project}:
            containers = run("docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}")
            networks = run("docker", "network", "ls", "-q", "--filter", f"label=com.docker.compose.project={project}")
            if containers.stdout.strip() or networks.stdout.strip():
                raise RuntimeError("Owned Compose resources remain after cleanup.")
        self.record("owned containers and networks removed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Already built manager/CPU worker image; never pulled.")
    parser.add_argument("--report", type=Path, help="New JSON receipt under evidence/.")
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    receipt = (REPO / (args.report or Path("evidence") / f"compose-lifecycle-{stamp}.json")).resolve()
    if not receipt.is_relative_to(REPO / "evidence"):
        parser.error("Receipts must stay under evidence/.")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open("x"):
        pass
    info = json.loads(run("docker", "image", "inspect", args.image).stdout)[0]
    report = {"status": "running", "image_id": info["Id"], "architecture": info["Architecture"],
              "image_revision": info["Config"]["Labels"].get("org.opencontainers.image.revision"),
              "source_commit": run("git", "rev-parse", "HEAD").stdout.strip(),
              "checkout_changes": run("git", "status", "--porcelain").stdout.splitlines(),
              "gpu_verified": False, "multi_device_network_verified": False,
              "physical_external_drive_verified": False, "test_lease_seconds": 16,
              "manager_limits": {"cpus": 0.5, "memory_mib": 512},
              "worker_limits": {"cpus": 2, "memory_mib": 2048}, "checks": []}
    temporary_roots = []
    try:
        for mode in ("single", "paired"):
            with tempfile.TemporaryDirectory(prefix="compose-lifecycle-", dir=REPO / "evidence") as temp:
                root = Path(temp)
                temporary_roots.append(root)
                for name in ("library", "output", "manager-state", "worker-state", "scratch"):
                    (root / name).mkdir(mode=0o777)
                    (root / name).chmod(0o777)
                hashes = {}
                fixtures = [("sample.mkv", 2, "160x96")]
                if mode == "single":
                    fixtures.append(("long.mkv", 180, "512x288"))
                for name, seconds, size in fixtures:
                    clip = root / "library" / name
                    run("ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=24",
                        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", str(seconds),
                        "-c:v", "libx264", "-preset", "ultrafast", "-bf", "0", "-c:a", "aac", str(clip))
                    hashes[name] = sha(clip)
                layout = Layout(root, args.image, mode, report)
                try:
                    layout.verify()
                    if hashes != {name: sha(root / "library" / name) for name in hashes}:
                        raise RuntimeError("Library original changed.")
                    layout.record("all originals unchanged")
                finally:
                    layout.close()
            report["checks"].append({"layout": mode, "name": "private temporary files removed", "status": "passed",
                                     "confirmed_absent": not root.exists()})
        report["status"] = "passed"
    except BaseException:
        report["status"] = "failed"
        raise
    finally:
        report["private_temporary_roots_removed"] = all(not root.exists() for root in temporary_roots)
        receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Compose lifecycle verification passed: {receipt}")


if __name__ == "__main__":
    main()
