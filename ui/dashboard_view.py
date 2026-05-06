"""
Vue Tableau de bord — statut connexion, stats, alertes.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QScrollArea
)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QFont
from app.app_state import get_state
from logs.logger import get_logger

log = get_logger("ui.dashboard")

CARD_STYLE = """
QFrame.card {
    background: #ffffff;
    border-radius: 12px;
    border: 1px solid #e5e7eb;
}
"""

KPI_STYLE = """
QFrame.kpi {
    background: #f8fafc;
    border-radius: 10px;
    border: 1px solid #e2e8f0;
    padding: 12px;
}
"""


class ConnectWorker(QThread):
    """Teste la connexion en arrière-plan."""
    result = Signal(bool, str, str)   # connected, url, version

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        from api.client import init_client
        client = init_client(self.url)
        connected = client.ping()
        version = client.get_server_version() or "" if connected else ""
        self.result.emit(connected, self.url, version)


class DashboardView(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._connect_state()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(30_000)  # rafraîchit toutes les 30s

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #f5f5f7; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: #f5f5f7;")
        main_layout = QVBoxLayout(content)
        main_layout.setContentsMargins(28, 28, 28, 28)
        main_layout.setSpacing(20)

        # Titre
        title = QLabel("Tableau de bord")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #1a1d27;")
        main_layout.addWidget(title)

        # ── Statut connexion ─────────────────────────────────────────────────
        conn_card = self._make_card()
        conn_layout = QHBoxLayout(conn_card)
        conn_layout.setContentsMargins(18, 16, 18, 16)

        self._conn_dot = QLabel("●")
        self._conn_dot.setStyleSheet("font-size: 18px; color: #dc2626;")
        self._conn_label = QLabel("Non connecté")
        self._conn_label.setStyleSheet("font-size: 14px; font-weight: 600; color: #374151;")
        self._conn_url = QLabel("")
        self._conn_url.setStyleSheet("font-size: 12px; color: #6b7280; margin-left: 8px;")
        self._conn_version = QLabel("")
        self._conn_version.setStyleSheet("font-size: 12px; color: #6b7280; margin-left: 8px;")

        self._btn_connect = QPushButton("Reconnecter")
        self._btn_connect.setStyleSheet("""
            QPushButton { background: #f97316; color: white; border: none;
                          border-radius: 8px; padding: 7px 16px; font-weight: 600; }
            QPushButton:hover { background: #ea580c; }
        """)
        self._btn_connect.clicked.connect(self._on_reconnect)

        conn_layout.addWidget(self._conn_dot)
        conn_layout.addWidget(self._conn_label)
        conn_layout.addWidget(self._conn_url)
        conn_layout.addWidget(self._conn_version)
        conn_layout.addStretch()
        conn_layout.addWidget(self._btn_connect)
        main_layout.addWidget(conn_card)

        # ── KPIs ─────────────────────────────────────────────────────────────
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(14)

        self._kpi_pending   = self._make_kpi("📋 En attente",   "0",    "#f59e0b")
        self._kpi_errors    = self._make_kpi("⚠️ Erreurs",       "0",    "#ef4444")
        self._kpi_uploaded  = self._make_kpi("✅ Uploadés",      "0",    "#22c55e")
        self._kpi_backup    = self._make_kpi("💾 Dern. sauveg.", "—",    "#3b82f6")

        kpi_grid.addWidget(self._kpi_pending,  0, 0)
        kpi_grid.addWidget(self._kpi_errors,   0, 1)
        kpi_grid.addWidget(self._kpi_uploaded, 0, 2)
        kpi_grid.addWidget(self._kpi_backup,   0, 3)
        main_layout.addLayout(kpi_grid)

        # ── Alertes ───────────────────────────────────────────────────────────
        self._alerts_card = self._make_card()
        alerts_layout = QVBoxLayout(self._alerts_card)
        alerts_layout.setContentsMargins(18, 16, 18, 16)
        alerts_title = QLabel("Alertes")
        alerts_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #374151;")
        alerts_layout.addWidget(alerts_title)
        self._alerts_container = QVBoxLayout()
        alerts_layout.addLayout(self._alerts_container)
        main_layout.addWidget(self._alerts_card)

        main_layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._refresh()

    def _make_card(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("class", "card")
        frame.setStyleSheet("""
            QFrame { background: #ffffff; border-radius: 12px;
                     border: 1px solid #e5e7eb; }
        """)
        return frame

    def _make_kpi(self, label: str, value: str, color: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{ background: #ffffff; border-radius: 10px;
                     border: 1px solid #e2e8f0; }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        lbl = QLabel(label)
        lbl.setStyleSheet("font-size: 12px; color: #6b7280;")
        val = QLabel(value)
        val.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {color};")
        val.setObjectName(f"kpi_val_{label}")
        layout.addWidget(lbl)
        layout.addWidget(val)
        return frame

    def _set_kpi_value(self, frame: QFrame, value: str):
        for child in frame.findChildren(QLabel):
            if child.objectName().startswith("kpi_val_"):
                child.setText(value)
                return

    def _connect_state(self):
        state = get_state()
        state.connection_changed.connect(self._on_connection_changed)
        state.auth_changed.connect(self._on_auth_changed)
        state.upload_stats_changed.connect(self._on_upload_stats)

    @Slot(bool, str)
    def _on_connection_changed(self, connected: bool, url: str):
        if connected:
            self._conn_dot.setStyleSheet("font-size: 18px; color: #22c55e;")
            self._conn_label.setText("Connecté")
            self._conn_url.setText(url)
        else:
            self._conn_dot.setStyleSheet("font-size: 18px; color: #dc2626;")
            self._conn_label.setText("Non connecté")
            self._conn_url.setText(url)
        self._refresh_alerts()

    @Slot(bool, str)
    def _on_auth_changed(self, authenticated: bool, username: str):
        if authenticated:
            self._conn_label.setText(f"Connecté · {username}")
        self._refresh_alerts()

    @Slot(int, int)
    def _on_upload_stats(self, pending: int, errors: int):
        self._set_kpi_value(self._kpi_pending, str(pending))
        self._set_kpi_value(self._kpi_errors, str(errors))

    def _refresh(self):
        from storage.repositories import get_last_backup
        backup = get_last_backup()
        if backup:
            finished = backup.get("finished_at", "")[:16].replace("T", " ")
            self._set_kpi_value(self._kpi_backup, finished or "—")
        self._refresh_alerts()

    def _refresh_alerts(self):
        # Vider
        while self._alerts_container.count():
            item = self._alerts_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        alerts = []
        state = get_state()

        if not state.is_connected:
            alerts.append(("🔴", "Serveur inaccessible", "#fef2f2", "#dc2626"))
        elif not state.is_authenticated:
            alerts.append(("🟡", "Non authentifié — connexion requise", "#fffbeb", "#d97706"))

        from storage.repositories import get_last_backup
        backup = get_last_backup()
        if not backup:
            alerts.append(("🔵", "Aucune sauvegarde effectuée", "#eff6ff", "#3b82f6"))

        if not alerts:
            ok = QLabel("✅  Tout est en ordre")
            ok.setStyleSheet("color: #16a34a; font-size: 13px; padding: 8px 0;")
            self._alerts_container.addWidget(ok)
            return

        for icon, text, bg, color in alerts:
            pill = QLabel(f"{icon}  {text}")
            pill.setStyleSheet(f"""
                QLabel {{ background: {bg}; color: {color}; border-radius: 8px;
                          padding: 8px 12px; font-size: 13px; font-weight: 500; }}
            """)
            self._alerts_container.addWidget(pill)

    def _on_reconnect(self):
        from storage.repositories import get_active_profile
        profile = get_active_profile()
        if not profile:
            return
        self._btn_connect.setEnabled(False)
        self._btn_connect.setText("Connexion…")
        self._worker = ConnectWorker(profile["url"])
        self._worker.result.connect(self._on_reconnect_result)
        self._worker.start()

    @Slot(bool, str, str)
    def _on_reconnect_result(self, connected: bool, url: str, version: str):
        self._btn_connect.setEnabled(True)
        self._btn_connect.setText("Reconnecter")
        state = get_state()
        state.set_connected(connected, url)
        if version:
            state.set_server_version(version)
        if connected:
            from api.auth_api import restore_session, get_current_user
            from storage.repositories import get_active_profile
            profile = get_active_profile()
            if profile and restore_session(profile["name"]):
                user = get_current_user()
                state.set_authenticated(True, user.get("email", "") if user else "")
