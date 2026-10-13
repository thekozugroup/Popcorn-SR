"""Optional worker/host handshake. The worker never receives Docker access."""

import json
import os
import socket
import time
import uuid
from pathlib import Path

from . import __version__
from .scratch import atomic_private_json


def read_message(path):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 32768:
            return {}
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


class WorkerUpdates:
    def __init__(self, directory=None):
        value = directory or os.environ.get("POPCORN_UPDATE_DIRECTORY")
        self.directory = Path(value) if value else None
        self.request_id = None
        if self.directory and not self.directory.is_dir():
            raise ValueError("Worker update folder is missing. Restore the host update service.")

    def request(self, identity=None):
        if not self.directory:
            raise ValueError("This worker has no host update service configured.")
        identity = str(uuid.UUID(identity)) if identity else str(uuid.uuid4())
        if read_message(self.directory / "request.json").get("id") != identity:
            atomic_private_json(self.directory / "request.json", {"id": identity, "requested_at": time.time()})
        self.request_id = identity
        return identity

    def status(self):
        result = {"version": __version__, "enabled": False}
        if not self.directory:
            return result
        controller = read_message(self.directory / "controller.json")
        updated = controller.get("updated_at", 0)
        result["enabled"] = isinstance(updated, (int, float)) and 0 <= time.time() - updated < 180
        result["automatic"] = controller.get("automatic") is True
        result["draining"] = self.draining()
        host = read_message(self.directory / "status.json")
        allowed = {"checking", "current", "waiting", "installing", "validating", "updated", "rolled_back", "failed"}
        if host.get("state") in allowed:
            result.update({"state": host["state"], "target_version": str(host.get("target_version", ""))[:32]})
        if self.request_id:
            result["request_id"] = self.request_id
        return result

    def runtime(self, capabilities, *, idle=False):
        if self.directory:
            atomic_private_json(self.directory / "runtime.json", {
                "version": __version__, "container": socket.gethostname(), "updated_at": time.time(),
                "idle": idle, "capabilities": {k: v for k, v in capabilities.items() if k != "updates"},
                "drain_id": read_message(self.directory / "drain.json").get("id"),
            })

    def draining(self):
        return bool(self.directory and (self.directory / "drain.json").exists())
