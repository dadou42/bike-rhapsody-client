"""
Repositories — accès aux données SQLite.
"""
import json
from datetime import datetime
from typing import Optional
from storage.local_db import db
from logs.logger import get_logger

log = get_logger("repositories")


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    row = db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    db().execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        (key, value),
    )
    db().commit()


def get_setting_json(key: str, default=None):
    raw = get_setting(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def set_setting_json(key: str, value) -> None:
    set_setting(key, json.dumps(value, ensure_ascii=False))


# ── Server profiles ───────────────────────────────────────────────────────────

def list_profiles() -> list[dict]:
    rows = db().execute(
        "SELECT * FROM server_profiles ORDER BY is_active DESC, name"
    ).fetchall()
    return [dict(r) for r in rows]


def get_active_profile() -> Optional[dict]:
    row = db().execute(
        "SELECT * FROM server_profiles WHERE is_active = 1 LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def upsert_profile(name: str, url: str, profile_type: str = "local") -> int:
    existing = db().execute(
        "SELECT id FROM server_profiles WHERE name = ?", (name,)
    ).fetchone()
    if existing:
        db().execute(
            "UPDATE server_profiles SET url=?, profile_type=? WHERE name=?",
            (url, profile_type, name),
        )
        db().commit()
        return existing["id"]
    cur = db().execute(
        "INSERT INTO server_profiles (name, url, profile_type, is_active) VALUES (?, ?, ?, 0)",
        (name, url, profile_type),
    )
    db().commit()
    return cur.lastrowid


def set_active_profile(profile_id: int) -> None:
    db().execute("UPDATE server_profiles SET is_active = 0")
    db().execute("UPDATE server_profiles SET is_active = 1 WHERE id = ?", (profile_id,))
    db().execute(
        "UPDATE server_profiles SET last_connected = datetime('now') WHERE id = ?",
        (profile_id,),
    )
    db().commit()


def delete_profile(profile_id: int) -> None:
    db().execute("DELETE FROM server_profiles WHERE id = ?", (profile_id,))
    db().commit()


# ── Backup jobs ───────────────────────────────────────────────────────────────

def create_backup_job(backup_type: str, destination: str) -> int:
    cur = db().execute(
        "INSERT INTO backup_jobs (backup_type, status, destination, started_at) VALUES (?, 'running', ?, datetime('now'))",
        (backup_type, destination),
    )
    db().commit()
    return cur.lastrowid


def finish_backup_job(job_id: int, archive_path: str, size_bytes: int, checksum: str) -> None:
    db().execute(
        """UPDATE backup_jobs
           SET status='done', archive_path=?, size_bytes=?, checksum=?,
               finished_at=datetime('now')
           WHERE id=?""",
        (archive_path, size_bytes, checksum, job_id),
    )
    db().commit()


def fail_backup_job(job_id: int, error: str) -> None:
    db().execute(
        "UPDATE backup_jobs SET status='failed', last_error=?, finished_at=datetime('now') WHERE id=?",
        (error, job_id),
    )
    db().commit()


def list_backup_jobs(limit: int = 20) -> list[dict]:
    rows = db().execute(
        "SELECT * FROM backup_jobs ORDER BY started_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_last_backup() -> Optional[dict]:
    row = db().execute(
        "SELECT * FROM backup_jobs WHERE status='done' ORDER BY finished_at DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None
