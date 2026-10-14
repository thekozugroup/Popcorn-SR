import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from popcorn_sr.auth import password_hash, password_matches
from popcorn_sr.config import Settings
from popcorn_sr.server import create_app


@pytest.fixture
def login_app(tmp_path):
    (tmp_path / "library").mkdir()
    cfg = Settings(
        tmp_path / "state",
        tmp_path / "library",
        tmp_path / "output",
        "legacy-token-that-must-not-grant-access",
        public_url="http://localhost",
    )
    app = create_app(cfg)
    with TestClient(app, base_url="http://localhost") as client:
        yield client, app


def login(client, password="admin"):
    return client.post("/api/login", json={"username": "admin", "password": password})


def change(client, password="test-password"):
    return client.post("/api/account/password", json={"username": "admin", "password": password})


def test_default_password_blocks_management_until_changed(login_app):
    client, app = login_app
    assert client.get("/api/auth/session").json()["default_login"]
    assert login(client).status_code == 200
    assert client.get("/api/state").status_code == 403
    assert client.post("/api/pair-codes").status_code == 403
    assert client.post("/api/auth/passkeys/register/options").status_code == 403
    assert change(client, "admin").status_code == 400
    assert change(client).status_code == 200
    assert client.get("/api/state").status_code == 200
    assert client.get("/api/auth/session").json()["offer_passkey"]
    assert app.state.auth.owner()["password_hash"] != "test-password"
    client.post("/api/auth/passkeys/skip").raise_for_status()
    assert not client.get("/api/auth/session").json()["offer_passkey"]


def test_password_is_salted_and_verifies_unicode():
    first, second = password_hash("example-\u2603-password"), password_hash("example-\u2603-password")
    assert first != second
    assert password_matches("example-\u2603-password", first)
    assert not password_matches("wrong", first)


def test_sessions_revoke_rotate_and_legacy_tokens_are_not_authorized(login_app):
    client, app = login_app
    assert (
        client.get(
            "/api/state", headers={"Authorization": "Bearer legacy-token-that-must-not-grant-access"}
        ).status_code
        == 401
    )
    response = login(client)
    assert (
        "HttpOnly" in response.headers["set-cookie"] and "SameSite=strict" in response.headers["set-cookie"]
    )
    old = client.cookies.get("popcorn_session")
    change(client).raise_for_status()
    assert client.cookies.get("popcorn_session") != old
    with TestClient(app, base_url="http://localhost") as other:
        other.cookies.set("popcorn_session", old)
        assert other.get("/api/state").status_code == 401
    client.post("/api/logout").raise_for_status()
    assert client.get("/api/state").status_code == 401
    assert login(client, "admin").status_code == 401
    assert login(client, "test-password").status_code == 200


def test_no_password_disclosure_and_attempt_limits(login_app):
    client, _ = login_app
    for _ in range(20):
        response = login(client, "incorrect")
        assert response.status_code == 401
        assert "incorrect" not in response.text.replace("Username or password is incorrect.", "")
    assert login(client).status_code == 429
    assert client.post("/api/login", json={"token": "legacy"}).status_code == 422


@pytest.mark.parametrize("origin", ["https://evil.example", "null", "http://localhost.evil.example"])
def test_authentication_blocks_cross_site_posts(login_app, origin):
    client, _ = login_app
    assert (
        client.post(
            "/api/login", json={"username": "admin", "password": "admin"}, headers={"Origin": origin}
        ).status_code
        == 403
    )


def test_passkeys_need_configured_origin_and_real_valid_response(login_app):
    client, _ = login_app
    login(client).raise_for_status()
    change(client).raise_for_status()
    response = client.post("/api/auth/passkeys/register/options")
    response.raise_for_status()
    value = response.json()
    assert value["options"]["authenticatorSelection"]["userVerification"] == "required"
    assert value["options"]["authenticatorSelection"]["residentKey"] == "required"
    invalid = {
        "request_id": value["request_id"],
        "credential": {"id": "bad", "type": "public-key", "response": {}},
    }
    assert client.post("/api/auth/passkeys/register/verify", json=invalid).status_code == 400
    assert client.post("/api/auth/passkeys/register/verify", json=invalid).status_code == 400
    assert client.get("/api/auth/session").json()["passkeys"] == 0
    assert client.post("/api/auth/passkeys/login/verify", json=invalid).status_code in (400, 401)
    with TestClient(client.app, base_url="http://wrong.example") as wrong:
        assert wrong.post("/api/auth/passkeys/login/options").status_code == 400


def test_expired_challenge_cannot_register(login_app):
    client, app = login_app
    login(client).raise_for_status()
    change(client).raise_for_status()
    value = client.post("/api/auth/passkeys/register/options").json()
    with app.state.store.connect() as db:
        db.execute("UPDATE auth_challenges SET expires=?", (time.time() - 1,))
    assert (
        client.post(
            "/api/auth/passkeys/register/verify", json={"request_id": value["request_id"], "credential": {}}
        ).status_code
        == 400
    )


def test_reset_does_not_remove_workers_and_preserves_credentials_on_restart(login_app):
    client, app = login_app
    login(client).raise_for_status()
    change(client).raise_for_status()
    store = app.state.store
    worker = store.pair(store.pair_code(), "Preserved", {"engines": ["resize"]}, {"path": "/scratch"})
    app.state.auth.provision("another-user", "new-password")
    assert store.worker(worker["token"])["id"] == worker["worker_id"]
    assert client.get("/api/state").status_code == 401
    from popcorn_sr.auth import Authentication

    restarted = Authentication(store, "http://localhost")
    assert restarted.owner()["username"] == "another-user"
    assert password_matches("new-password", restarted.owner()["password_hash"])


def test_initialization_migrates_legacy_sessions_without_removing_saved_data(tmp_path):
    from popcorn_sr.auth import Authentication
    from popcorn_sr.db import Store

    store = Store(tmp_path)
    with store.connect() as db:
        db.execute("INSERT INTO sessions VALUES (?,?)", ("legacy", time.time() + 3600))
    auth = Authentication(store)
    assert auth.owner()["must_change"]
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
    assert sqlite3.connect(store.path).execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_login_body_is_bounded_and_validation_never_echoes_password(login_app):
    client, _ = login_app
    secret = "private-password" * 30
    response = client.post("/api/login", json={"username": "admin", "password": secret})
    assert response.status_code == 422
    assert secret not in response.text
    assert client.post("/api/login", content="x" * 65537).status_code == 413
    assert client.post("/api/auth/passkeys/login/verify", content="x" * 65537).status_code == 413


def test_secure_cookie_on_configured_https_origin(tmp_path):
    app = create_app(
        Settings(
            tmp_path / "state",
            tmp_path / "library",
            tmp_path / "output",
            public_url="https://popcorn.example:9445",
        )
    )
    with TestClient(app, base_url="http://popcorn.example:9445") as client:
        response = login(client)
        assert "Secure" in response.headers["set-cookie"]
        assert client.get("/api/auth/session").json()["passkey_available"]


def test_expired_session_cannot_manage_or_enroll(login_app):
    client, app = login_app
    login(client).raise_for_status()
    change(client).raise_for_status()
    with app.state.store.connect() as db:
        db.execute("UPDATE sessions SET expires=?", (time.time() - 1,))
    assert client.get("/api/state").status_code == 401
    assert client.post("/api/auth/passkeys/register/options").status_code == 401
    assert not client.get("/api/auth/session").json()["authenticated"]


@pytest.mark.parametrize(
    "origin",
    [
        "http://popcorn.example",
        "https://popcorn.example/path",
        "https://user:password@popcorn.example",
        "https://popcorn.example?invalid",
    ],
)
def test_passkey_origin_rejects_unsafe_configuration(tmp_path, origin):
    from popcorn_sr.auth import Authentication
    from popcorn_sr.db import Store

    with pytest.raises(ValueError, match="HTTPS origin"):
        Authentication(Store(tmp_path), origin)
