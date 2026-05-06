"""
Worker d'upload — QThread persistant qui consomme la file SQLite.
Gère retry, progression, pause/reprise.
"""
from datetime import datetime
from PySide6.QtCore import QThread, Signal
from storage.local_db import db
from sync.retry_policy import next_retry_at, should_retry, MAX_RETRIES
from logs.logger import get_logger

log = get_logger("sync.worker")


class UploadWorker(QThread):
    """
    Worker qui tourne en fond et traite la file d'attente.

    Signaux :
      file_started(media_id, filename)
      file_progress(media_id, bytes_done, bytes_total)
      file_done(media_id, server_id)
      file_failed(media_id, error, retry_in)
      queue_stats(pending, errors, done)
    """

    file_started  = Signal(int, str)        # media_id, filename
    file_progress = Signal(int, int, int)   # media_id, done, total
    file_done     = Signal(int, str)        # media_id, server_media_id
    file_failed   = Signal(int, str, str)   # media_id, error, retry_label
    queue_stats   = Signal(int, int, int)   # pending, errors, done

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paused = False
        self._stop = False

    def pause(self) -> None:
        self._paused = True
        log.info("Upload worker paused")

    def resume(self) -> None:
        self._paused = False
        log.info("Upload worker resumed")

    def stop(self) -> None:
        self._stop = True
        self._paused = False

    def run(self):
        log.info("Upload worker started")
        while not self._stop:
            if self._paused:
                self.msleep(500)
                continue

            job = self._next_job()
            if job is None:
                self.msleep(3000)  # rien à faire, attendre
                self._emit_stats()
                continue

            self._process_job(job)
            self._emit_stats()

        log.info("Upload worker stopped")

    def _next_job(self) -> dict | None:
        """Récupère le prochain job uploadable (pending ou retry dû)."""
        rows = db().execute(
            """SELECT q.*, m.local_path, m.original_name, m.sha256, m.activity_id
               FROM upload_queue q
               JOIN media_files m ON m.id = q.media_id
               WHERE q.status IN ('pending', 'retrying')
                 AND (q.next_retry_at IS NULL OR q.next_retry_at <= datetime('now'))
               ORDER BY q.priority DESC, q.created_at ASC
               LIMIT 1"""
        ).fetchone()
        return dict(rows) if rows else None

    def _process_job(self, job: dict) -> None:
        media_id   = job["media_id"]
        queue_id   = job["id"]
        local_path = job["local_path"]
        filename   = job["original_name"] or local_path.split("/")[-1]
        sha256     = job.get("sha256", "")
        activity_id = job.get("activity_id")

        log.info("Uploading: %s (queue_id=%d)", filename, queue_id)
        self.file_started.emit(media_id, filename)

        # Marquer comme en cours
        self._set_queue_status(queue_id, "uploading")
        self._set_media_status(media_id, "uploading")

        try:
            from api.media_api import upload_media

            def on_progress(done: int, total: int):
                self.file_progress.emit(media_id, done, total)

            result = upload_media(
                local_path,
                activity_id=str(activity_id) if activity_id else None,
                progress_cb=on_progress,
            )
            server_id = str(result.get("id", ""))

            # Succès
            db().execute(
                "UPDATE upload_queue SET status='done', updated_at=datetime('now') WHERE id=?",
                (queue_id,),
            )
            db().execute(
                "UPDATE media_files SET status='uploaded', server_media_id=?, updated_at=datetime('now') WHERE id=?",
                (server_id, media_id),
            )
            db().commit()
            log.info("Upload done: %s → server_id=%s", filename, server_id)
            self.file_done.emit(media_id, server_id)

        except Exception as e:
            error_msg = str(e)
            retry_count = job.get("retry_count", 0) + 1
            log.warning("Upload failed: %s — %s (retry %d)", filename, error_msg, retry_count)

            if retry_count >= MAX_RETRIES:
                # Abandon définitif
                db().execute(
                    """UPDATE upload_queue
                       SET status='failed', retry_count=?, last_error=?, updated_at=datetime('now')
                       WHERE id=?""",
                    (retry_count, error_msg, queue_id),
                )
                db().execute(
                    "UPDATE media_files SET status='failed', updated_at=datetime('now') WHERE id=?",
                    (media_id,),
                )
                db().commit()
                self.file_failed.emit(media_id, error_msg, "Abandon")
            else:
                # Planifier retry
                nra = next_retry_at(retry_count)
                from sync.retry_policy import retry_delay_label
                label = retry_delay_label(retry_count)
                db().execute(
                    """UPDATE upload_queue
                       SET status='retrying', retry_count=?, last_error=?,
                           next_retry_at=?, updated_at=datetime('now')
                       WHERE id=?""",
                    (retry_count, error_msg, nra, queue_id),
                )
                db().execute(
                    "UPDATE media_files SET status='failed', updated_at=datetime('now') WHERE id=?",
                    (media_id,),
                )
                db().commit()
                self.file_failed.emit(media_id, error_msg, label)

    def _set_queue_status(self, queue_id: int, status: str) -> None:
        db().execute(
            "UPDATE upload_queue SET status=?, updated_at=datetime('now') WHERE id=?",
            (status, queue_id),
        )
        db().commit()

    def _set_media_status(self, media_id: int, status: str) -> None:
        db().execute(
            "UPDATE media_files SET status=?, updated_at=datetime('now') WHERE id=?",
            (status, media_id),
        )
        db().commit()

    def _emit_stats(self) -> None:
        try:
            row = db().execute(
                """SELECT
                     SUM(CASE WHEN status IN ('pending','retrying','uploading') THEN 1 ELSE 0 END) as pending,
                     SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as errors,
                     SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done
                   FROM upload_queue"""
            ).fetchone()
            if row:
                self.queue_stats.emit(
                    row["pending"] or 0,
                    row["errors"] or 0,
                    row["done"] or 0,
                )
        except Exception:
            pass
