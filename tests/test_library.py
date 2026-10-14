import hashlib
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from popcorn_sr.config import Library, Settings
from popcorn_sr.models import Recipe
from popcorn_sr.server import create_app
from tests.conftest import pair_worker


def library_client(tmp_path, clip):
    movies, shows = tmp_path / "movies", tmp_path / "shows"
    movie = movies / "A film (2026)"
    season = shows / "A show" / "Season 01"
    movie.mkdir(parents=True)
    season.mkdir(parents=True)
    shutil.copyfile(clip, movie / "A film.mkv")
    shutil.copyfile(clip, season / "Episode 01.mkv")
    cfg = Settings(tmp_path / "new-state", clip.parent, tmp_path / "copies", reserve_bytes=0,
                   library_name="Test clips", libraries=(Library("movies", "Movies", movies),
                                                         Library("shows", "TV shows", shows)))
    app = create_app(cfg)
    app.state.auth.provision("admin", "library-test-password")
    client = TestClient(app)
    client.post("/api/login", json={"username": "admin", "password": "library-test-password"}).raise_for_status()
    return client, cfg


def test_multiple_libraries_keep_legacy_sources_and_stream_selected_movie(setup, tmp_path):
    _, _, _, clip = setup
    client, cfg = library_client(tmp_path, clip)
    with client:
        choices = client.get("/api/state").json()["storage"]["libraries"]
        assert [item["name"] for item in choices] == ["Test clips", "Movies", "TV shows"]
        assert client.get("/api/library").json()["items"][0]["path"] == "sample.mkv"
        listing = client.get("/api/library", params={"directory": "@sources/movies"}).json()
        assert listing["items"][0]["path"] == "@sources/movies/A film (2026)"
        path = listing["items"][0]["path"] + "/A film.mkv"
        original = hashlib.sha256(cfg.source(path).read_bytes()).hexdigest()
        metadata = client.get("/api/library/metadata", params={"path": path})
        assert metadata.status_code == 200 and metadata.json()["width"] == 128
        frame = client.get("/api/library/frame", params={"path": path, "seconds": 0})
        assert frame.status_code == 200 and frame.content.startswith(b"\x89PNG")
        credentials, _ = pair_worker(client)
        response = client.post("/api/jobs", json={"path": path, "recipe": Recipe(scale=1).model_dump()})
        assert response.status_code == 200 and response.json()["path"] == path
        headers = {"Authorization": f"Bearer {credentials['token']}"}
        job = client.post("/api/worker/claim", headers=headers).json()["job"]
        assert job["path"] == path
        headers["X-Job-Lease"] = job["lease"]
        source = client.get(f"/api/worker/jobs/{job['id']}/source", headers=headers)
        assert source.status_code == 200 and hashlib.sha256(source.content).hexdigest() == original
        assert hashlib.sha256(cfg.source(path).read_bytes()).hexdigest() == original
        client.cookies.clear()
        assert client.get("/api/library", params={"directory": "@sources/movies"}).status_code == 401
        assert client.get("/api/state", headers=headers).status_code == 401


def test_library_filter_pagination_and_mount_escape_guards(setup, tmp_path):
    _, _, _, clip = setup
    client, cfg = library_client(tmp_path, clip)
    movies = cfg.libraries[0].path
    for index in range(103):
        (movies / f"Other film {index:03}").mkdir()
    (movies / "hidden-link").symlink_to(cfg.library, target_is_directory=True)
    (movies / ".hidden").mkdir()
    (movies / "readme.txt").write_text("not a video")
    with client:
        page = client.get("/api/library", params={"directory": "@sources/movies"}).json()
        assert page["total"] == 104 and len(page["items"]) == 100
        assert len(client.get("/api/library", params={"directory": "@sources/movies", "offset": 100}).json()["items"]) == 4
        filtered = client.get("/api/library", params={"directory": "@sources/movies", "search": "FILM (2026)"}).json()
        assert filtered["total"] == 1
        assert client.get("/api/library", params={"directory": "@sources/movies", "search": "missing"}).json()["total"] == 0
        for path in ("@sources", "@sources/missing", "@sources/movies/../../library", "@sources/movies/hidden-link"):
            assert client.get("/api/library", params={"directory": path}).status_code == 400
        for path in ("@sources/movies/hidden-link/sample.mkv", "@sources/missing/sample.mkv", "@sources/movies/../sample.mkv"):
            assert client.get("/api/library/metadata", params={"path": path}).status_code == 400
            assert client.post("/api/jobs", json={"path": path, "recipe": Recipe().model_dump()}).status_code == 400
        shutil.rmtree(cfg.libraries[1].path)
        assert client.get("/api/library", params={"directory": "@sources/shows"}).status_code == 400
        assert client.get("/api/library", params={"directory": "@sources/movies"}).status_code == 200


def test_extra_library_configuration_and_output_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("POPCORN_EXTRA_LIBRARIES", json.dumps([{"id": "movies", "name": "Movies", "path": str(tmp_path / "movies")}]))
    assert Settings.from_env().libraries[0].path == tmp_path / "movies"
    for identity in ("../escape", "@sources", "default", "MOVIES", ""):
        with pytest.raises(ValueError):
            Library(identity, "Movies", tmp_path)
    with pytest.raises(ValueError, match="unique"):
        Settings(tmp_path / "state", tmp_path / "library", tmp_path / "output",
                 libraries=(Library("movies", "Movies", tmp_path / "movies"), Library("movies", "Duplicate", tmp_path / "other")))
    for output in (tmp_path / "movies", tmp_path / "movies" / "outputs", tmp_path):
        with pytest.raises(RuntimeError, match="separate"):
            create_app(Settings(tmp_path / "state", tmp_path / "library", output,
                                libraries=(Library("movies", "Movies", tmp_path / "movies"),)))
    assert not (tmp_path / "movies" / "outputs").exists()
