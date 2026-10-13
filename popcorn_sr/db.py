import contextlib
import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from pathlib import Path

from .dlss import compatible_recipe


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self, state: Path):
        state.mkdir(parents=True, exist_ok=True)
        self.path = state / "popcorn.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS pair_codes (hash TEXT PRIMARY KEY, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS workers (
                    id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                    capabilities TEXT NOT NULL, scratch TEXT NOT NULL, seen REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, path TEXT NOT NULL, recipe TEXT NOT NULL, target TEXT,
                    status TEXT NOT NULL, worker_id TEXT, lease TEXT, lease_until REAL,
                    progress REAL NOT NULL DEFAULT 0, stage TEXT NOT NULL DEFAULT 'Waiting for a worker',
                    created REAL NOT NULL, updated REAL NOT NULL, source TEXT NOT NULL,
                    result TEXT, error TEXT
                );
                CREATE INDEX IF NOT EXISTS jobs_queue ON jobs(status, created);
            """)

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def pair_code(self):
        code = secrets.token_urlsafe(24)
        with self.connect() as db:
            db.execute("DELETE FROM pair_codes WHERE expires < ?", (time.time(),))
            db.execute("INSERT INTO pair_codes VALUES (?, ?)", (digest(code), time.time() + 600))
        return code

    def pair(self, code, name, capabilities, scratch):
        identity, token = str(uuid.uuid4()), secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            used = db.execute(
                "DELETE FROM pair_codes WHERE hash=? AND expires>?", (digest(code), time.time())
            )
            if used.rowcount != 1:
                raise ValueError("Pairing code expired or was already used. Create a new code.")
            db.execute(
                "INSERT INTO workers VALUES (?, ?, ?, ?, ?, ?, 0)",
                (identity, digest(token), name, json.dumps(capabilities), json.dumps(scratch), time.time()),
            )
        return {"worker_id": identity, "token": token}

    def worker(self, token):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM workers WHERE token_hash=? AND revoked=0", (digest(token),)
            ).fetchone()
        return dict(row) if row else None

    def workers(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM workers ORDER BY name").fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "online": r["seen"] > time.time() - 45 and not r["revoked"],
                "revoked": bool(r["revoked"]),
                "capabilities": json.loads(r["capabilities"]),
                "scratch": json.loads(r["scratch"]),
                "last_seen": r["seen"],
            }
            for r in rows
        ]

    def touch(self, worker_id, capabilities=None, scratch=None):
        with self.connect() as db:
            db.execute("UPDATE workers SET seen=? WHERE id=? AND revoked=0", (time.time(), worker_id))
            if capabilities is not None:
                db.execute(
                    "UPDATE workers SET capabilities=?, scratch=? WHERE id=?",
                    (json.dumps(capabilities), json.dumps(scratch), worker_id),
                )

    def add_job(self, path, recipe, source, target=None):
        identity = str(uuid.uuid4())
        now = time.time()
        with self.connect() as db:
            db.execute(
                "INSERT INTO jobs (id,path,recipe,target,status,created,updated,source) VALUES (?,?,?,?,'queued',?,?,?)",
                (identity, path, json.dumps(recipe), target, now, now, json.dumps(source)),
            )
        return self.job(identity)

    @staticmethod
    def unpack(row):
        if row is None:
            return None
        item = dict(row)
        for key in ("recipe", "source", "result"):
            item[key] = json.loads(item[key]) if item[key] else None
        return item

    def job(self, identity):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identity,)).fetchone()
        return self.unpack(row)

    def jobs(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 200").fetchall()
        return [self.unpack(r) for r in rows]

    def expire(self, db):
        db.execute(
            "UPDATE jobs SET status='failed', stage='Worker disconnected', error='Worker lease expired. Review and retry.', lease=NULL, updated=? WHERE status='running' AND lease_until<?",
            (time.time(), time.time()),
        )

    def claim(self, worker, lease_seconds):
        caps = json.loads(worker["capabilities"])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.expire(db)
            if db.execute(
                "SELECT 1 FROM jobs WHERE worker_id=? AND status='running'", (worker["id"],)
            ).fetchone():
                return None
            rows = db.execute(
                "SELECT * FROM jobs WHERE status='queued' AND (target IS NULL OR target=?) ORDER BY created",
                (worker["id"],),
            ).fetchall()
            for row in rows:
                recipe = json.loads(row["recipe"])
                if not compatible_recipe(recipe, caps, json.loads(row["source"])):
                    continue
                if recipe["engine"] != "resize" and recipe["encoder"] != "nvidia":
                    continue
                lease = secrets.token_urlsafe(32)
                db.execute(
                    "UPDATE jobs SET status='running',worker_id=?,lease=?,lease_until=?,updated=?,stage='Receiving source' WHERE id=?",
                    (worker["id"], lease, time.time() + lease_seconds, time.time(), row["id"]),
                )
                updated = db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone()
                return self.unpack(updated)
        return None

    def owned(self, identity, worker_id, lease):
        job = self.job(identity)
        if (
            not job
            or job["status"] != "running"
            or job["worker_id"] != worker_id
            or not secrets.compare_digest(job["lease"] or "", lease)
            or job["lease_until"] < time.time()
        ):
            raise ValueError("Job was cancelled, reassigned, or its lease expired.")
        return job

    def heartbeat(self, identity, worker_id, lease, progress, stage, seconds):
        with self.connect() as db:
            changed = db.execute(
                "UPDATE jobs SET lease_until=?,progress=?,stage=?,updated=? WHERE id=? AND worker_id=? AND lease=? AND status='running' AND lease_until>?",
                (
                    time.time() + seconds,
                    progress,
                    stage,
                    time.time(),
                    identity,
                    worker_id,
                    lease,
                    time.time(),
                ),
            )
            return changed.rowcount == 1

    def finish(self, identity, worker_id, lease, result):
        with self.connect() as db:
            changed = db.execute(
                "UPDATE jobs SET status='completed',progress=100,stage='Ready',result=?,lease=NULL,updated=? WHERE id=? AND worker_id=? AND lease=? AND status='running' AND lease_until>?",
                (json.dumps(result), time.time(), identity, worker_id, lease, time.time()),
            )
            return changed.rowcount == 1

    def fail(self, identity, worker_id, lease, error):
        with self.connect() as db:
            db.execute(
                "UPDATE jobs SET status='failed',stage='Needs attention',error=?,lease=NULL,updated=? WHERE id=? AND worker_id=? AND lease=? AND status='running'",
                (error, time.time(), identity, worker_id, lease),
            )

    def cancel(self, identity):
        with self.connect() as db:
            db.execute(
                "UPDATE jobs SET status='cancelled',stage='Cancelled',lease=NULL,updated=? WHERE id=? AND status IN ('queued','running')",
                (time.time(), identity),
            )

    def retry(self, identity):
        with self.connect() as db:
            changed = db.execute(
                "UPDATE jobs SET status='queued',stage='Waiting for a worker',lease=NULL,worker_id=NULL,progress=0,error=NULL,updated=? WHERE id=? AND status IN ('failed','cancelled')",
                (time.time(), identity),
            )
            return changed.rowcount == 1
