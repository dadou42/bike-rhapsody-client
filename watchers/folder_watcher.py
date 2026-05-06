"""
Surveillance de dossiers via watchdog.
Détecte les nouveaux fichiers et les envoie en scan.
"""
import time
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal, QThread
from logs.logger import get_logger

log = get_logger("watchers.folder")

# watchdog est optionnel — on dégrade gracieusement si absent
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    log.warning("watchdog not installed — folder watching disabled. pip install watchdog")


class _MediaEventHandler:
    """Handler watchdog qui émet un signal quand un nouveau fichier média arrive."""

    def __init__(self, callback: Callable[[str], None]):
        self._cb = callback
        self._pending: dict[str, float] = {}  # path → last_mtime

    def on_created(self, event) -> None:
        if event.is_directory:
            return
        from media.media_model import ALL_MEDIA_EXTENSIONS
        path = Path(event.src_path)
        if path.suffix.lower() in ALL_MEDIA_EXTENSIONS:
            # Attendre que le fichier soit stable (fin de copie)
            self._pending[str(path)] = time.time()

    def on_modified(self, event) -> None:
        if not event.is_directory:
            self._pending[str(event.src_path)] = time.time()

    def flush_stable(self, stability_s: float = 3.0) -> list[str]:
        """Retourne les fichiers stables (non modifiés depuis stability_s secondes)."""
        now = time.time()
        stable = [p for p, t in self._pending.items() if (now - t) >= stability_s]
        for p in stable:
            del self._pending[p]
        return stable


if HAS_WATCHDOG:
    from watchdog.events import FileSystemEventHandler

    class _WatchdogHandler(FileSystemEventHandler):
        def __init__(self, handler: "_MediaEventHandler"):
            super().__init__()
            self._h = handler

        def on_created(self, event):
            self._h.on_created(event)

        def on_modified(self, event):
            self._h.on_modified(event)


class FolderWatcherThread(QThread):
    """
    Thread qui surveille une liste de dossiers et émet new_file(path)
    pour chaque fichier média stable détecté.
    """
    new_file = Signal(str)

    def __init__(self, paths: list[str], parent=None):
        super().__init__(parent)
        self._paths = [str(p) for p in paths]
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self):
        if not HAS_WATCHDOG:
            log.warning("watchdog not available, FolderWatcherThread exiting")
            return

        handler = _MediaEventHandler(lambda p: None)
        wd_handler = _WatchdogHandler(handler)
        observer = Observer()

        for path in self._paths:
            if Path(path).exists():
                observer.schedule(wd_handler, path, recursive=True)
                log.info("Watching: %s", path)
            else:
                log.warning("Watch path not found (skipped): %s", path)

        observer.start()
        log.info("Folder watcher started (%d paths)", len(self._paths))

        try:
            while not self._stop:
                self.msleep(1000)
                for fpath in handler.flush_stable(stability_s=3.0):
                    log.info("New stable file detected: %s", fpath)
                    self.new_file.emit(fpath)
        finally:
            observer.stop()
            observer.join()
            log.info("Folder watcher stopped")


class FolderWatcher(QObject):
    """
    Interface haut-niveau pour la surveillance de dossiers.
    """
    new_file = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: FolderWatcherThread | None = None
        self._paths: list[str] = []

    def set_paths(self, paths: list[str]) -> None:
        self._paths = paths

    def start(self) -> None:
        if not self._paths:
            return
        self.stop()
        self._thread = FolderWatcherThread(self._paths)
        self._thread.new_file.connect(self.new_file)
        self._thread.start()

    def stop(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.stop()
            self._thread.wait(3000)
            self._thread = None

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.isRunning())
