from fastapi.testclient import TestClient

import popcorn_sr.server as server
from popcorn_sr.config import Settings


def test_missing_web_build_keeps_manager_available(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr(server, "__file__", str(tmp_path / "unbuilt" / "server.py"))
    cfg = Settings(tmp_path / "state", library, tmp_path / "output", "test-access-key-32-characters-long")
    with TestClient(server.create_app(cfg)) as client:
        assert client.get("/health").status_code == 200
        page = client.get("/")
        assert page.status_code == 503
        assert "npm run build" in page.text
        assert client.get("/api/state").status_code == 401
