"""
Gestionnaire d'uploads — singleton qui pilote le worker.
"""
from PySide6.QtCore import QObject, Signal
from sync.worker import UploadWorker
from app.app_state import get_state
from logs.logger import get_logger

log = get_logger("sync.manager")


class UploadManager(QObject):
    """Singleton qui expose l'UploadWorker et propage les stats vers AppState."""

    file_started  = Signal(int, str)
    file_progress = Signal(int, int, int)
    file_done     = Signal(int, str)
    file_failed   = Signal(int, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = UploadWorker()
        self._worker.file_started.connect(self.file_started)
        self._worker.file_progress.connect(self.file_progress)
        self._worker.file_done.connect(self.file_done)
        self._worker.file_failed.connect(self.file_failed)
        self._worker.queue_stats.connect(self._on_stats)

    def start(self) -> None:
        if not self._worker.isRunning():
            self._worker.start()
            log.info("Upload manager started")

    def pause(self) -> None:
        self._worker.pause()

    def resume(self) -> None:
        self._worker.resume()

    def stop(self) -> None:
        self._worker.stop()
        self._worker.wait(3000)

    def is_paused(self) -> bool:
        return self._worker._paused

    def add_to_queue(self, media_db_id: int, priority: int = 0) -> None:
        from storage.local_db import db
        # Éviter les doublons
        exists = db().execute(
            "SELECT id FROM upload_queue WHERE media_id=? AND status NOT IN ('done','failed')",
            (media_db_id,),
        ).fetchone()
        if exists:
            return
        db().execute(
            "INSERT INTO upload_queue (media_id, priority, status) VALUES (?,?,'pending')",
            (media_db_id, priority),
        )
        db().commit()
        log.debug("Added media_id=%d to queue (priority=%d)", media_db_id, priority)

    def retry_failed(self) -> int:
        """Remet tous les jobs failed en pending. Retourne le nombre remis en queue."""
        from storage.local_db import db
        cur = db().execute(
            """UPDATE upload_queue
               SET status='pending', retry_count=0, next_retry_at=NULL, last_error=NULL,
                   updated_at=datetime('now')
               WHERE status='failed'"""
        )
        db().commit()
        count = cur.rowcount
        if count:
            log.info("Retrying %d failed uploads", count)
        return count

    def _on_stats(self, pending: int, errors: int, done: int) -> None:
        get_state().set_upload_stats(pending, errors)


# Singleton
_manager: UploadManager | None = None


def get_upload_manager() -> UploadManager:
    global _manager
    if _manager is None:
        _manager = UploadManager()
    return _manager
