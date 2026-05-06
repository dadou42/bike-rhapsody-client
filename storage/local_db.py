"""
Bootstrap SQLite — crée les tables si nécessaire, gère les migrations.
"""
import sqlite3
from pathlib import Path
from config.defaults import DB_PATH
from logs.logger import get_logger

log = get_logger("db")

SCHEMA_VERSION = 1

MIGRATIONS = {
    1: [
        """
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS server_profiles (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            url          TEXT NOT NULL,
            profile_type TEXT DEFAULT 'local',
            is_active    INTEGER DEFAULT 0,
            last_connected TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS media_files (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            local_path           TEXT NOT NULL,
            original_name        TEXT,
            file_type            TEXT,
            mime_type            TEXT,
            size_bytes           INTEGER,
            sha256               TEXT,
            status               TEXT DEFAULT 'discovered',
            activity_id          TEXT,
            activity_match_score REAL,
            gps_lat              REAL,
            gps_lon              REAL,
            gps_alt              REAL,
            captured_at          TEXT,
            tags                 TEXT,
            notes                TEXT,
            server_media_id      TEXT,
            created_at           TEXT DEFAULT (datetime('now')),
            updated_at           TEXT DEFAULT (datetime('now'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS upload_queue (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id        INTEGER NOT NULL REFERENCES media_files(id),
            status          TEXT DEFAULT 'pending',
            priority        INTEGER DEFAULT 0,
            retry_count     INTEGER DEFAULT 0,
            last_error      TEXT,
            last_attempt_at TEXT,
            next_retry_at   TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            updated_at      TEXT DEFAULT (datetime('now'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS activities_cache (
            activity_id       TEXT PRIMARY KEY,
            name              TEXT,
            start_time        TEXT,
            end_time          TEXT,
            sport_type        TEXT,
            distance_m        REAL,
            elevation_gain_m  REAL,
            city              TEXT,
            country           TEXT,
            raw_json          TEXT,
            updated_at        TEXT DEFAULT (datetime('now'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS backup_jobs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            backup_type   TEXT,
            status        TEXT DEFAULT 'pending',
            destination   TEXT,
            archive_path  TEXT,
            manifest_path TEXT,
            started_at    TEXT,
            finished_at   TEXT,
            size_bytes    INTEGER,
            checksum      TEXT,
            last_error    TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS migration_jobs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            source_server TEXT,
            target_server TEXT,
            status        TEXT DEFAULT 'pending',
            started_at    TEXT,
            finished_at   TEXT,
            report_path   TEXT,
            last_error    TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        )
        """,
    ]
}


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1").fetchone()
        return row["version"] if row else 0
    except sqlite3.OperationalError:
        return 0


def migrate(conn: sqlite3.Connection) -> None:
    current = get_schema_version(conn)
    log.info("DB schema version: %d, target: %d", current, SCHEMA_VERSION)

    for version in range(current + 1, SCHEMA_VERSION + 1):
        log.info("Applying migration v%d", version)
        for sql in MIGRATIONS[version]:
            conn.execute(sql)
        conn.execute(
            "INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (version,)
        )
        conn.commit()
        log.info("Migration v%d applied", version)


_conn: sqlite3.Connection | None = None


def init_db() -> sqlite3.Connection:
    global _conn
    _conn = get_connection()
    migrate(_conn)
    log.info("SQLite ready at %s", DB_PATH)
    return _conn


def db() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("DB not initialized — call init_db() first")
    return _conn
