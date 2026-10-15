#!/usr/bin/env python3
"""Host service for one explicitly configured Popcorn SR worker. No sidecar/socket mount."""

import argparse
import fcntl
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

REPOSITORIES = {
    "ngx": "ghcr.io/thekozugroup/popcorn-sr",
    "ai": "ghcr.io/thekozugroup/popcorn-sr",
    "cpu": "ghcr.io/thekozugroup/popcorn-sr",
    "restoration": "ghcr.io/thekozugroup/popcorn-sr",
}
STATES = {"checking", "current", "waiting", "installing", "validating", "updated", "rolled_back", "failed"}


def read(path):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
            return {}
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write(path, value, mode=0o600):
    fd, temporary = tempfile.mkstemp(prefix=".update-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(value, output)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("Image has no valid release version.")
    return tuple(map(int, value.split(".")))


def retains_features(previous, current):
    if current.get("initialization") != "ready":
        return False
    if previous.get("resolution_rules") and not current.get("resolution_rules"):
        return False
    for key in ("engines", "encoders"):
        if not set(previous.get(key, [])).issubset(current.get(key, [])):
            return False
    for key in ("dlss_sr", "dlss_frame_generation", "rtx_vsr", "rtx_hdr", "flashvsr"):
        old, new = previous.get(key, {}), current.get(key, {})
        for field in ("settings", "pipelines", "upscalers", "qualities", "temporal_qualities", "codecs"):
            if not all(item in new.get(field, []) for item in old.get(field, [])):
                return False
        if new.get("maximum_factor", 0) < old.get("maximum_factor", 0):
            return False
        for field in ("resolution_targets", "custom_size", "strength", "lossless"):
            if old.get(field) and not new.get(field):
                return False
    return True


class Updater:
    def __init__(self, config_path):
        if config_path.is_symlink() or config_path.stat().st_uid != os.geteuid() or config_path.stat().st_mode & 0o022:
            raise ValueError("Update configuration must be owned and writable only by the host service user.")
        self.config_path = config_path.resolve()
        self.config = read(self.config_path)
        self.control = Path(self.config["control"])
        self.state = self.config_path.parent / "update-state.json"
        self.repository = REPOSITORIES[self.config["role"]]
        self.channel = {"ngx": "ngx-stable", "ai": "ai-stable", "cpu": "stable", "restoration": "restoration-stable"}[self.config["role"]]
        seconds = self.config.get("validation_seconds", 1200)
        if type(seconds) is not int or not 1 <= seconds <= 1200:
            raise ValueError("Worker validation timeout must be between 1 and 1200 seconds.")
        self.variable = {"ngx": "POPCORN_NGX_IMAGE", "ai": "POPCORN_AI_IMAGE", "cpu": "POPCORN_IMAGE", "restoration": "POPCORN_RESTORATION_IMAGE"}[self.config["role"]]
        if not self.control.is_absolute() or not self.control.is_dir():
            raise ValueError("Update control folder is missing.")
        for key in ("compose", "environment"):
            path = Path(self.config[key])
            if not path.is_absolute() or not path.is_file() or path.is_symlink():
                raise ValueError("Install fixed host-owned Compose and environment files.")
            if path.stat().st_uid != os.geteuid() or path.stat().st_mode & 0o022:
                raise ValueError("Host configuration must not be writable by another user.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", self.config["project"]):
            raise ValueError("Invalid Compose project name.")
        self.compose = ["docker", "compose", "--project-name", self.config["project"],
                        "--env-file", self.config["environment"], "-f", self.config["compose"]]

    def command(self, *args, image=None, timeout=30):
        env = os.environ.copy()
        if image:
            env[self.variable] = image
        result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=timeout)
        if result.returncode:
            # Never echo Docker configuration/environment (which can contain pairing credentials).
            raise RuntimeError("Docker operation failed. Check the host service journal and registry access.")
        return result.stdout.strip()

    def container(self):
        identities = self.command(*self.compose, "ps", "--all", "--quiet", "worker").splitlines()
        if len(identities) != 1 or not re.fullmatch(r"[0-9a-f]{12,64}", identities[0]):
            raise ValueError("Expected exactly one installed worker in the configured project.")
        result = json.loads(self.command("docker", "inspect", identities[0]))[0]
        labels = result["Config"].get("Labels") or {}
        if labels.get("com.docker.compose.project") != self.config["project"] or labels.get("com.docker.compose.service") != "worker":
            raise ValueError("Worker identity does not match the configured project.")
        return result

    def image(self, reference):
        result = json.loads(self.command("docker", "image", "inspect", reference))[0]
        labels = result["Config"].get("Labels") or {}
        release = labels.get("org.opencontainers.image.version")
        version(release)
        revision = labels.get("org.opencontainers.image.revision", "")
        if not re.fullmatch(r"[0-9a-f]{40}", revision) or labels.get("org.opencontainers.image.source") != "https://github.com/thekozugroup/Popcorn-SR":
            raise ValueError("Image provenance does not identify a Popcorn SR release.")
        return result, release, revision

    def status(self, state, target=""):
        assert state in STATES
        write(self.control / "status.json", {"state": state, "target_version": target, "updated_at": time.time()}, 0o644)

    def runtime(self, container, *, drain=None):
        value = read(self.control / "runtime.json")
        updated = value.get("updated_at", 0)
        if not isinstance(updated, int | float) or not 0 <= time.time() - updated < 30:
            return {}
        if value.get("container") != container["Config"]["Hostname"] or not container["State"]["Running"]:
            return {}
        if drain and (not value.get("idle") or value.get("drain_id") != drain):
            return {}
        if drain and value.get("capabilities", {}).get("initialization") != "ready":
            return {}
        return value

    def recreate(self, image):
        self.command(*self.compose, "up", "--detach", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "worker", image=image, timeout=120)

    def validate(self, image, target, previous):
        started = time.monotonic()
        while time.monotonic() - started < self.config.get("validation_seconds", 1200):
            container = self.container()
            if container["Image"] != image:
                raise ValueError("Replacement worker does not use the staged image.")
            live = self.runtime(container)
            if live.get("version") == target:
                capabilities = live.get("capabilities", {})
                if capabilities.get("initialization") == "failed":
                    raise ValueError("Replacement worker failed its genuine support checks.")
                if capabilities.get("initialization") == "ready":
                    if not retains_features(previous, capabilities):
                        raise ValueError("Replacement worker lost previously verified processing features.")
                    return
            time.sleep(3)
        raise ValueError("Replacement worker support checks timed out.")

    def clear_request(self, identity):
        if read(self.control / "request.json").get("id") == identity:
            (self.control / "request.json").unlink(missing_ok=True)

    def run(self):
        now = time.time()
        write(self.control / "controller.json", {"updated_at": now, "automatic": self.config.get("automatic", True)}, 0o644)
        saved = read(self.state)
        transaction = saved.get("transaction")
        request = read(self.control / "request.json")
        identity = request.get("id")
        try:
            identity = str(uuid.UUID(identity)) if isinstance(identity, str) else None
        except ValueError:
            identity = None
        if not transaction:
            if not identity and (not self.config.get("automatic", True) or now - saved.get("checked_at", 0) < 21600):
                return
            self.status("checking")
            current = self.container()
            old, old_version, _ = self.image(current["Image"])
            self.command("docker", "pull", self.repository + ":" + self.channel, timeout=900)
            candidate, target, revision = self.image(self.repository + ":" + self.channel)
            if candidate["Architecture"] != old["Architecture"] or candidate["Os"] != "linux":
                raise ValueError("Release architecture does not match the installed worker.")
            saved["checked_at"] = now
            if version(target) <= version(old_version) or (not identity and saved.get("rejected_revision") == revision):
                self.status("current", old_version)
                write(self.state, saved)
                self.clear_request(identity)
                return
            digests = [d for d in candidate.get("RepoDigests", []) if d.startswith(self.repository + "@sha256:")]
            if len(digests) != 1 or not re.fullmatch(re.escape(self.repository) + r"@sha256:[0-9a-f]{64}", digests[0]):
                raise ValueError("Release has no unique immutable registry digest.")
            transaction = {"id": str(uuid.uuid4()), "request_id": identity, "old_image": old["Id"],
                           "old_version": old_version, "image": candidate["Id"], "reference": digests[0],
                           "version": target, "revision": revision, "phase": "waiting"}
            saved["transaction"] = transaction
            write(self.state, saved)
        write(self.control / "drain.json", {"id": transaction["id"]}, 0o644)
        current = self.container()
        if transaction["phase"] == "waiting":
            live = self.runtime(current, drain=transaction["id"])
            if not live:
                self.status("waiting", transaction["version"])
                return
            if current["Image"] != transaction["old_image"]:
                raise ValueError("Installed worker changed during the update. Check the host configuration.")
            transaction["previous_features"] = live.get("capabilities", {})
            transaction["phase"] = "validating"
            write(self.state, saved)
        try:
            self.status("installing", transaction["version"])
            self.recreate(transaction["reference"])
            self.status("validating", transaction["version"])
            self.validate(transaction["image"], transaction["version"], transaction["previous_features"])
            # Persist selection in a root-owned override, preserving every environment secret/path.
            self.persist_image(transaction["reference"])
            self.status("updated", transaction["version"])
            saved["previous_image"] = transaction["old_image"]
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            self.recreate(transaction["old_image"])
            self.validate(transaction["old_image"], transaction["old_version"], transaction["previous_features"])
            self.status("rolled_back", transaction["version"])
            saved["rejected_revision"] = transaction["revision"]
        saved.pop("transaction", None)
        saved["checked_at"] = time.time()
        write(self.state, saved)
        self.clear_request(transaction["request_id"])
        (self.control / "drain.json").unlink(missing_ok=True)

    def persist_image(self, reference):
        path = Path(self.config["environment"])
        lines = [line for line in path.read_text().splitlines() if not line.startswith(self.variable + "=")]
        fd, temporary = tempfile.mkstemp(prefix=".environment-", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as output:
                output.write("\n".join([*lines, self.variable + "=" + reference]) + "\n")
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    updater = Updater(args.config)
    with (args.config.parent / "update.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        try:
            updater.run()
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            updater.status("failed")
            raise SystemExit("Worker update failed; check the host configuration and registry. No credentials are logged.") from None


if __name__ == "__main__":
    main()
