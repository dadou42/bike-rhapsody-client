"""
État global partagé de l'application — singleton thread-safe.
"""
from dataclasses import dataclass, field
from typing import Optional
from PySide6.QtCore import QObject, Signal


class AppState(QObject):
    """
    Singleton central. Émet des signaux Qt quand l'état change
    pour que les vues se mettent à jour sans couplage direct.
    """

    # Signaux
    connection_changed = Signal(bool, str)   # (connected, server_url)
    auth_changed = Signal(bool, str)         # (authenticated, username)
    server_version_changed = Signal(str)
    upload_stats_changed = Signal(int, int)  # (pending, errors)
    update_available = Signal(str)           # version disponible

    def __init__(self):
        super().__init__()
        self.is_connected: bool = False
        self.is_authenticated: bool = False
        self.server_url: str = ""
        self.server_version: str = ""
        self.username: str = ""
        self.pending_uploads: int = 0
        self.error_uploads: int = 0
        self.last_sync: Optional[str] = None
        self.last_backup: Optional[str] = None

    def set_connected(self, connected: bool, url: str = "") -> None:
        self.is_connected = connected
        self.server_url = url
        self.connection_changed.emit(connected, url)

    def set_authenticated(self, authenticated: bool, username: str = "") -> None:
        self.is_authenticated = authenticated
        self.username = username
        self.auth_changed.emit(authenticated, username)

    def set_server_version(self, version: str) -> None:
        self.server_version = version
        self.server_version_changed.emit(version)

    def set_upload_stats(self, pending: int, errors: int) -> None:
        self.pending_uploads = pending
        self.error_uploads = errors
        self.upload_stats_changed.emit(pending, errors)


# Singleton
_state: Optional[AppState] = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState()
    return _state
