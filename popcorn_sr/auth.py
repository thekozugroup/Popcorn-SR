"""Single-owner password and verified WebAuthn authentication. Worker pairing is separate."""

import base64
import hashlib
import json
import re
import secrets
import threading
import time
from collections import OrderedDict
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .db import digest


def password_hash(password):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return "scrypt$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(key).decode()


def password_matches(password, encoded):
    _, salt, expected = encoded.split("$")
    key = hashlib.scrypt(password.encode(), salt=base64.urlsafe_b64decode(salt), n=16384, r=8, p=1, dklen=32)
    return secrets.compare_digest(key, base64.urlsafe_b64decode(expected))


def credentials_valid(username, password):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", username):
        raise ValueError("Use 1–64 letters, numbers, dots, dashes or underscores for your username.")
    if not 6 <= len(password) <= 256 or password == "admin":
        raise ValueError("Choose a new password with at least 6 characters.")


class Login(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=256)


class PasswordChange(Login):
    current_password: str = Field(default="", max_length=256)


class CredentialResponse(BaseModel):
    request_id: str = Field(max_length=128)
    credential: dict


class Authentication:
    def __init__(self, store, public_url=""):
        self.store = store
        self.origin = public_url.rstrip("/")
        parsed = urlsplit(self.origin)
        if self.origin and (
            parsed.scheme not in ("https", "http")
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or (parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1"))
        ):
            raise ValueError(
                "POPCORN_PUBLIC_URL must be an HTTPS origin (or HTTP localhost for development)."
            )
        self.rp_id = parsed.hostname or ""
        self.hash_slots = threading.BoundedSemaphore(2)
        self.limit_lock = threading.Lock()
        self.attempts = OrderedDict()
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS owner (
                    id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL,
                    password_hash TEXT NOT NULL, user_handle BLOB NOT NULL,
                    must_change INTEGER NOT NULL, passkey_prompted INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS passkeys (
                    credential_id BLOB PRIMARY KEY, public_key BLOB NOT NULL, sign_count INTEGER NOT NULL,
                    rp_id TEXT NOT NULL, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_challenges (
                    id TEXT PRIMARY KEY, challenge BLOB NOT NULL, kind TEXT NOT NULL,
                    session_hash TEXT NOT NULL, expires REAL NOT NULL
                );
            """)
            if "created" not in {r[1] for r in db.execute("PRAGMA table_info(sessions)")}:
                db.execute("ALTER TABLE sessions ADD COLUMN created REAL NOT NULL DEFAULT 0")
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM owner").fetchone():
                db.execute(
                    "INSERT INTO owner VALUES (1,?,?,?,?,0)",
                    ("admin", password_hash("admin"), secrets.token_bytes(32), 1),
                )
                # Invalidate the obsolete access-key sessions only during this migration.
                db.execute("DELETE FROM sessions")

    def owner(self):
        with self.store.connect() as db:
            return dict(db.execute("SELECT * FROM owner WHERE id=1").fetchone())

    def provision(self, username, password):
        credentials_valid(username, password)
        with self.hash_slots:
            encoded = password_hash(password)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE owner SET username=?,password_hash=?,user_handle=?,must_change=0,passkey_prompted=0 WHERE id=1",
                (username, encoded, secrets.token_bytes(32)),
            )
            db.execute("DELETE FROM sessions")
            db.execute("DELETE FROM auth_challenges")
            db.execute("DELETE FROM passkeys")

    def rate(self, request):
        address = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self.limit_lock:
            recent = [t for t in self.attempts.pop(address, []) if now - t < 60]
            if len(recent) >= 20:
                self.attempts[address] = recent
                raise HTTPException(429, "Too many sign-in attempts. Wait a minute and try again.")
            self.attempts[address] = [*recent, now]
            while len(self.attempts) > 1024:
                self.attempts.popitem(last=False)

    def session(self, request, *, allow_initial=False):
        token = request.cookies.get("popcorn_session", "")
        with self.store.connect() as db:
            row = db.execute(
                "SELECT * FROM sessions WHERE hash=? AND expires>?", (digest(token), time.time())
            ).fetchone()
        if not token or not row:
            raise HTTPException(401, "Sign in to manage your library.")
        owner = self.owner()
        if owner["must_change"] and not allow_initial:
            raise HTTPException(403, "Change the initial password before using Popcorn SR.")
        return owner, dict(row)

    def secure(self, request):
        return request.url.scheme == "https" or bool(
            self.origin
            and self.origin.startswith("https://")
            and request.headers.get("host") == urlsplit(self.origin).netloc
        )

    def new_session(self, request, response, expected_hash=None):
        token, now = secrets.token_urlsafe(32), time.time()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if (
                expected_hash
                and db.execute("SELECT password_hash FROM owner WHERE id=1").fetchone()[0] != expected_hash
            ):
                raise HTTPException(401, "Your login changed. Sign in again.")
            db.execute(
                "DELETE FROM sessions WHERE hash=?", (digest(request.cookies.get("popcorn_session", "")),)
            )
            db.execute("DELETE FROM sessions WHERE expires<?", (now,))
            db.execute(
                "INSERT INTO sessions(hash,expires,created) VALUES (?,?,?)", (digest(token), now + 86400, now)
            )
        response.set_cookie(
            "popcorn_session",
            token,
            httponly=True,
            samesite="strict",
            secure=self.secure(request),
            max_age=86400,
        )

    def info(self, request):
        try:
            owner, _ = self.session(request, allow_initial=True)
        except HTTPException:
            with self.store.connect() as db:
                has_passkeys = bool(
                    db.execute("SELECT 1 FROM passkeys WHERE rp_id=? LIMIT 1", (self.rp_id,)).fetchone()
                )
            return {
                "authenticated": False,
                "default_login": bool(self.owner()["must_change"]),
                "passkey_url": self.origin or None,
                "passkey_available": self.passkey_context(request),
                "has_passkeys": has_passkeys,
            }
        with self.store.connect() as db:
            count = db.execute("SELECT count(*) FROM passkeys WHERE rp_id=?", (self.rp_id,)).fetchone()[0]
        return {
            "authenticated": True,
            "username": owner["username"],
            "must_change_password": bool(owner["must_change"]),
            "offer_passkey": not owner["passkey_prompted"],
            "passkeys": count,
            "passkey_available": self.passkey_context(request),
            "passkey_url": self.origin or None,
        }

    def passkey_context(self, request):
        return bool(self.origin and request.headers.get("host") == urlsplit(self.origin).netloc)

    def require_passkey_context(self, request):
        if not self.passkey_context(request):
            raise HTTPException(400, "Open the configured HTTPS address to use passkeys.")

    def challenge(self, request, response, kind, value, session_hash=""):
        identity = secrets.token_urlsafe(32)
        with self.store.connect() as db:
            db.execute("DELETE FROM auth_challenges WHERE expires<?", (time.time(),))
            db.execute(
                "INSERT INTO auth_challenges VALUES (?,?,?,?,?)",
                (digest(identity), value, kind, session_hash, time.time() + 120),
            )
        response.set_cookie(
            "popcorn_challenge",
            identity,
            httponly=True,
            samesite="strict",
            secure=self.secure(request),
            max_age=120,
        )
        return identity

    def consume(self, request, response, body, kind):
        cookie = request.cookies.get("popcorn_challenge", "")
        if not cookie or not secrets.compare_digest(cookie, body.request_id):
            raise HTTPException(400, "Passkey request expired. Try again.")
        with self.store.connect() as db:
            row = db.execute(
                "DELETE FROM auth_challenges WHERE id=? RETURNING *", (digest(cookie),)
            ).fetchone()
        response.delete_cookie(
            "popcorn_challenge", secure=self.secure(request), httponly=True, samesite="strict"
        )
        if not row or row["expires"] < time.time() or row["kind"] != kind:
            raise HTTPException(400, "Passkey request expired. Try again.")
        if kind == "register" and row["session_hash"] != digest(request.cookies.get("popcorn_session", "")):
            raise HTTPException(400, "Sign in again before adding a passkey.")
        return row["challenge"]

    def router(self):
        router = APIRouter()

        @router.get("/api/auth/session")
        def status(request: Request):
            return self.info(request)

        @router.post("/api/login")
        def login(body: Login, request: Request, response: Response):
            self.rate(request)
            owner = self.owner()
            with self.hash_slots:
                valid = password_matches(body.password, owner["password_hash"])
            if not valid or body.username.casefold() != owner["username"].casefold():
                raise HTTPException(401, "Username or password is incorrect.")
            self.new_session(request, response, owner["password_hash"])
            return {"ok": True}

        @router.post("/api/account/password")
        def change(body: PasswordChange, request: Request, response: Response):
            owner, session = self.session(request, allow_initial=True)
            self.rate(request)
            with self.hash_slots:
                if not (owner["must_change"] and session["created"] > time.time() - 600):
                    if not password_matches(body.current_password, owner["password_hash"]):
                        raise HTTPException(401, "Current password is incorrect.")
                try:
                    credentials_valid(body.username, body.password)
                except ValueError as exc:
                    raise HTTPException(400, str(exc)) from exc
                if password_matches(body.password, owner["password_hash"]):
                    raise HTTPException(400, "Choose a different password.")
                encoded = password_hash(body.password)
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                changed = db.execute(
                    "UPDATE owner SET username=?,password_hash=?,must_change=0 WHERE id=1 AND password_hash=?",
                    (body.username, encoded, owner["password_hash"]),
                )
                if changed.rowcount != 1:
                    raise HTTPException(409, "Your login changed. Sign in again.")
                db.execute("DELETE FROM sessions")
                db.execute("DELETE FROM auth_challenges")
            self.new_session(request, response, encoded)
            return {"ok": True}

        @router.post("/api/logout")
        def logout(request: Request, response: Response):
            with self.store.connect() as db:
                db.execute(
                    "DELETE FROM sessions WHERE hash=?", (digest(request.cookies.get("popcorn_session", "")),)
                )
            response.delete_cookie(
                "popcorn_session", secure=self.secure(request), httponly=True, samesite="strict"
            )
            return {"ok": True}

        @router.post("/api/auth/passkeys/skip")
        def skip(request: Request):
            self.session(request)
            with self.store.connect() as db:
                db.execute("UPDATE owner SET passkey_prompted=1 WHERE id=1")
            return {"ok": True}

        @router.post("/api/auth/passkeys/register/options")
        def register_options(request: Request, response: Response):
            self.require_passkey_context(request)
            owner, session = self.session(request)
            if session["created"] < time.time() - 900:
                raise HTTPException(401, "Sign in again to add a passkey.")
            self.rate(request)
            with self.store.connect() as db:
                keys = db.execute(
                    "SELECT credential_id FROM passkeys WHERE rp_id=?", (self.rp_id,)
                ).fetchall()
            options = generate_registration_options(
                rp_id=self.rp_id,
                rp_name="Popcorn SR",
                user_id=owner["user_handle"],
                user_name=owner["username"],
                exclude_credentials=[PublicKeyCredentialDescriptor(id=k[0]) for k in keys],
                authenticator_selection=AuthenticatorSelectionCriteria(
                    resident_key=ResidentKeyRequirement.REQUIRED,
                    user_verification=UserVerificationRequirement.REQUIRED,
                ),
            )
            identity = self.challenge(request, response, "register", options.challenge, session["hash"])
            return {"request_id": identity, "options": json.loads(options_to_json(options))}

        @router.post("/api/auth/passkeys/register/verify")
        def register_verify(body: CredentialResponse, request: Request, response: Response):
            self.require_passkey_context(request)
            owner, session = self.session(request)
            challenge = self.consume(request, response, body, "register")
            if len(json.dumps(body.credential)) > 65536:
                raise HTTPException(400, "Passkey response is too large.")
            try:
                result = verify_registration_response(
                    credential=body.credential,
                    expected_challenge=challenge,
                    expected_rp_id=self.rp_id,
                    expected_origin=self.origin,
                    require_user_verification=True,
                )
            except Exception:
                raise HTTPException(400, "Passkey could not be verified. Try again.") from None
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute("SELECT * FROM owner WHERE id=1").fetchone()
                active = db.execute(
                    "SELECT 1 FROM sessions WHERE hash=? AND expires>?", (session["hash"], time.time())
                ).fetchone()
                if not active or current["user_handle"] != owner["user_handle"]:
                    raise HTTPException(401, "Sign in again before adding a passkey.")
                db.execute(
                    "INSERT OR IGNORE INTO passkeys VALUES (?,?,?,?,?)",
                    (
                        result.credential_id,
                        result.credential_public_key,
                        result.sign_count,
                        self.rp_id,
                        time.time(),
                    ),
                )
                db.execute("UPDATE owner SET passkey_prompted=1 WHERE id=1")
            return {"ok": True}

        @router.post("/api/auth/passkeys/login/options")
        def login_options(request: Request, response: Response):
            self.require_passkey_context(request)
            self.rate(request)
            options = generate_authentication_options(
                rp_id=self.rp_id, user_verification=UserVerificationRequirement.REQUIRED
            )
            identity = self.challenge(request, response, "login", options.challenge)
            return {"request_id": identity, "options": json.loads(options_to_json(options))}

        @router.post("/api/auth/passkeys/login/verify")
        def login_verify(body: CredentialResponse, request: Request, response: Response):
            self.require_passkey_context(request)
            challenge = self.consume(request, response, body, "login")
            try:
                credential_id = base64url_to_bytes(body.credential["id"])
                user_handle = body.credential["response"].get("userHandle")
                with self.store.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    owner = db.execute("SELECT * FROM owner WHERE id=1").fetchone()
                    if user_handle and base64url_to_bytes(user_handle) != owner["user_handle"]:
                        raise ValueError("Wrong user")
                    key = db.execute(
                        "SELECT * FROM passkeys WHERE credential_id=? AND rp_id=?",
                        (credential_id, self.rp_id),
                    ).fetchone()
                    if not key or owner["must_change"]:
                        raise ValueError("Unknown credential")
                    result = verify_authentication_response(
                        credential=body.credential,
                        expected_challenge=challenge,
                        expected_rp_id=self.rp_id,
                        expected_origin=self.origin,
                        credential_public_key=key["public_key"],
                        credential_current_sign_count=key["sign_count"],
                        require_user_verification=True,
                    )
                    db.execute(
                        "UPDATE passkeys SET sign_count=? WHERE credential_id=?",
                        (result.new_sign_count, credential_id),
                    )
            except Exception:
                raise HTTPException(
                    401, "Passkey could not be verified. Try again or use your password."
                ) from None
            self.new_session(request, response, owner["password_hash"])
            return {"ok": True}

        return router
