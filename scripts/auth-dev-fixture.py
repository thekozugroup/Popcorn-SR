#!/usr/bin/env python3
"""Disposable, empty installation for genuine browser sign-in/passkey checks."""

import tempfile
from pathlib import Path

import uvicorn

from popcorn_sr.config import Settings
from popcorn_sr.server import create_app

with tempfile.TemporaryDirectory(prefix="popcorn-auth-browser-") as directory:
    root = Path(directory)
    (root / "library").mkdir()
    app = create_app(
        Settings(root / "state", root / "library", root / "output", public_url="http://localhost:18878")
    )
    uvicorn.run(app, host="127.0.0.1", port=18878, access_log=False)
