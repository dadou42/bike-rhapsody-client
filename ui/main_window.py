"""
Fenêtre principale — sidebar + QStackedWidget.
"""
import json
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget,
    QMessageBox, QLabel
)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QCloseEvent

from ui.components.sidebar import Sidebar
from ui.dashboard_view import DashboardView
from ui.settings_view import SettingsView
from ui.logs_view import LogsView
from ui.placeholder_view import PlaceholderView
from app.app_state import get_state
from logs.logger import get_logger

log = get_logger("ui.main_window")


def _load_version() -> str:
    candidates = [
        Path(__file__).parent.parent / "version.json",
        Path(__file__).parent / "version.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text())["version"]
            except Exception:
                pass
    return "1.0.0"


class UpdateCheckWorker(QThread):
    update_found = Signal(object)

    def run(self):
        from updater.updater import check_for_update
        release = check_for_update()
        self.update_found.emit(release)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._version = _load_version()
        self._setup_window()
        self._build_ui()
        self._connect_state()
        self._schedule_update_check()

    def _setup_window(self):
        self.setWindowTitle("Bike Rhapsody Client")
        self.setMinimumSize(1000, 680)
        self.resize(1200, 760)
        # Style global
        self.setStyleSheet("""
            QMainWindow { background: #f5f5f7; }
            QToolTip { background: #1c1c1e; color: #fff; border: none;
                       border-radius: 6px; padding: 4px 8px; }
        """)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        self._sidebar = Sidebar()
        self._sidebar.set_version(self._version)
        self._sidebar.page_requested.connect(self._switch_page)
        root.addWidget(self._sidebar)

        # Pages
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: #f5f5f7;")

        self._pages: dict[str, QWidget] = {
            "dashboard":  DashboardView(),
            "import":     PlaceholderView("Import médias", "📥", "Phase 2 — scan, miniatures, déduplication"),
            "queue":      PlaceholderView("File d'attente", "📋", "Phase 2 — upload persistant avec retry"),
            "activities": PlaceholderView("Activités", "🚴", "Phase 3 — matching médias ↔ activités"),
            "backup":     PlaceholderView("Sauvegarde", "💾", "Phase 5 — BDD + fichiers + manifest"),
            "migration":  PlaceholderView("Migration serveur", "🔄", "Phase 6 — assistant source/cible"),
            "history":    PlaceholderView("Historique", "📅", "Phase 2+ — historique des opérations"),
            "settings":   SettingsView(),
            "logs":       LogsView(),
        }

        for page in self._pages.values():
            self._stack.addWidget(page)

        root.addWidget(self._stack)

        # Page par défaut
        self._switch_page("dashboard")

    def _switch_page(self, key: str) -> None:
        page = self._pages.get(key)
        if page:
            self._stack.setCurrentWidget(page)
            self._sidebar.set_active(key)
            log.debug("Switched to page: %s", key)

    def _connect_state(self):
        state = get_state()
        state.connection_changed.connect(self._on_connection_changed)
        state.auth_changed.connect(self._on_auth_changed)
        state.update_available.connect(self._on_update_available)

    @Slot(bool, str)
    def _on_connection_changed(self, connected: bool, url: str):
        status = f"✅ {url}" if connected else f"🔴 Hors ligne"
        self.setWindowTitle(f"Bike Rhapsody Client — {status}")

    @Slot(bool, str)
    def _on_auth_changed(self, authenticated: bool, username: str):
        if authenticated:
            log.info("User authenticated: %s", username)

    def _schedule_update_check(self):
        # Vérifie les mises à jour 8s après le démarrage
        QTimer.singleShot(8000, self._check_updates)

    def _check_updates(self):
        from storage.repositories import get_setting
        if get_setting("auto_check_updates", "1") != "0":
            self._update_worker = UpdateCheckWorker()
            self._update_worker.update_found.connect(self._on_update_found)
            self._update_worker.start()

    @Slot(object)
    def _on_update_found(self, release):
        if release is None:
            return
        get_state().update_available.emit(release.version)
        # Proposer la mise à jour
        reply = QMessageBox.question(
            self,
            "Mise à jour disponible",
            f"La version {release.version} est disponible.\n\n"
            f"Télécharger et installer maintenant ?\n\n"
            f"L'application redémarrera automatiquement.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Déléguer à la vue Settings pour le téléchargement
            settings_view = self._pages.get("settings")
            if settings_view:
                settings_view._download_update(release)

    def closeEvent(self, event: QCloseEvent) -> None:
        log.info("Application closing")
        from api.client import get_client
        try:
            get_client().close()
        except Exception:
            pass
        event.accept()
