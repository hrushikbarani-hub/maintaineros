import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import UTC
from pathlib import Path

from .models import ActionUpdate, RepositorySnapshot


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS snapshots (
                    sequence INTEGER PRIMARY KEY, digest TEXT UNIQUE NOT NULL,
                    repository TEXT NOT NULL, captured_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS snapshots_repo ON snapshots(repository, captured_at DESC);
                CREATE TABLE IF NOT EXISTS actions (
                    repository TEXT NOT NULL, category TEXT NOT NULL,
                    state TEXT NOT NULL, note TEXT NOT NULL,
                    PRIMARY KEY(repository, category)
                );
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            db.row_factory = sqlite3.Row
            with db:
                yield db
        finally:
            db.close()

    def save(self, snapshot: RepositorySnapshot):
        # Canonical UTC strings make chronological SQL ordering reliable.
        snapshot = snapshot.model_copy(update={"captured_at": snapshot.captured_at.astimezone(UTC)})
        payload = snapshot.model_dump_json()
        digest = hashlib.sha256(payload.encode()).hexdigest()
        with self.connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO snapshots(digest, repository, captured_at, payload) VALUES(?,?,?,?)",
                (digest, snapshot.full_name, snapshot.captured_at.isoformat(), payload),
            )

    def history(self, repository: str, limit: int = 60) -> list[RepositorySnapshot]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT payload FROM snapshots WHERE repository=? ORDER BY captured_at DESC, sequence DESC LIMIT ?",
                (repository.lower(), limit),
            ).fetchall()
        return [RepositorySnapshot.model_validate_json(row["payload"]) for row in rows]

    def latest(self) -> list[RepositorySnapshot]:
        with self.connection() as db:
            rows = db.execute("""SELECT payload FROM (
                SELECT payload, repository, ROW_NUMBER() OVER(
                    PARTITION BY repository ORDER BY captured_at DESC, sequence DESC
                ) AS rank FROM snapshots) WHERE rank=1 ORDER BY repository""").fetchall()
        return [RepositorySnapshot.model_validate_json(row["payload"]) for row in rows]

    def actions(self, repository: str) -> dict:
        with self.connection() as db:
            rows = db.execute(
                "SELECT category, state, note FROM actions WHERE repository=?",
                (repository.lower(),),
            ).fetchall()
        return {row["category"]: {"state": row["state"], "note": row["note"]} for row in rows}

    def set_action(self, repository: str, category: str, update: ActionUpdate):
        with self.connection() as db:
            db.execute(
                "INSERT INTO actions VALUES(?,?,?,?) ON CONFLICT(repository,category) DO UPDATE SET state=excluded.state,note=excluded.note",
                (repository.lower(), category, update.state, update.note),
            )
