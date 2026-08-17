from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BacktestJobStore:
    """Small persistent queue; strategy results remain canonical JSON files."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=10000")
        return db

    def _init(self) -> None:
        with self.connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS backtest_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    request_json TEXT NOT NULL,
                    run_id TEXT,
                    result_path TEXT,
                    error TEXT,
                    quality_json TEXT,
                    submitted_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS jobs_status_submitted ON backtest_jobs(status, submitted_at)")

    def create(self, job_id: str, request: dict[str, Any]) -> dict[str, Any]:
        submitted = _now()
        with self.connect() as db:
            db.execute(
                "INSERT INTO backtest_jobs(job_id,status,progress,request_json,submitted_at) VALUES(?,?,?,?,?)",
                (job_id, "queued", 0, json.dumps(request, ensure_ascii=False), submitted),
            )
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute("SELECT * FROM backtest_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._decode(row)

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM backtest_jobs ORDER BY submitted_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._decode(row) for row in rows]

    def claim_next(self) -> dict[str, Any] | None:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT job_id FROM backtest_jobs WHERE status='queued' ORDER BY submitted_at LIMIT 1").fetchone()
            if row is None:
                db.commit()
                return None
            started = _now()
            changed = db.execute(
                "UPDATE backtest_jobs SET status='running',progress=5,started_at=? WHERE job_id=? AND status='queued'",
                (started, row["job_id"]),
            ).rowcount
            db.commit()
        return self.get(row["job_id"]) if changed else None

    def update(self, job_id: str, *, status: str, progress: int, **fields: Any) -> dict[str, Any]:
        allowed = {"run_id", "result_path", "error", "quality_json", "finished_at"}
        values: dict[str, Any] = {"status": status, "progress": max(0, min(100, int(progress)))}
        values.update({key: value for key, value in fields.items() if key in allowed})
        assignments = ",".join(f"{key}=?" for key in values)
        with self.connect() as db:
            db.execute(f"UPDATE backtest_jobs SET {assignments} WHERE job_id=?", (*values.values(), job_id))
        return self.get(job_id)

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["request"] = json.loads(item.pop("request_json"))
        quality = item.pop("quality_json")
        item["quality"] = json.loads(quality) if quality else None
        return item
