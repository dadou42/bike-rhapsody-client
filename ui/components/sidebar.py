"""
Sidebar de navigation — style macOS sombre.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QSpacerItem, QSizePolicy
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

SIDEBAR_ITEMS = [
    ("dashboard",   "🏠", "Tableau de bord"),
    ("import",      "📥", "Import médias"),
    ("queue",       "📋", "File d'attente"),
    ("activities",  "🚴", "Activités"),
    ("backup",      "💾", "Sauvegarde"),
    ("migration",   "🔄", "Migration"),
    ("history",     "📅", "Historique"),
    ("settings",    "⚙️",  "Paramètres"),
    ("logs",        "📄", "Logs"),
]

SIDEBAR_STYLE = """
QWidget#sidebar {
    background: #1c1c1e;
    border-right: 1px solid #2c2c2e;
}
QPushButton.nav-btn {
    background: transparent;
    border: none;
    border-radius: 8px;
    color: #ebebf5cc;
    text-align: left;
    padding: 10px 14px;
    font-size: 13px;
}
QPushButton.nav-btn:hover {
    background: rgba(255,255,255,0.08);
    color: #ffffff;
}
QPushButton.nav-btn[active="true"] {
    background: rgba(249,115,22,0.18);
    color: #f97316;
    font-weight: bold;
}
"""


class Sidebar(QWidget):
    page_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(210)
        self.setStyleSheet(SIDEBAR_STYLE)

        self._buttons: dict[str, QPushButton] = {}
        self._active_key: str = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(2)

        # Logo / titre
        title = QLabel("🚴 Bike Rhapsody")
        title.setStyleSheet("color:#f97316; font-size:14px; font-weight:700; padding:8px 8px 16px 8px;")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(title)

        # Boutons de navigation
        for key, icon, label in SIDEBAR_ITEMS:
            btn = QPushButton(f"  {icon}  {label}")
            btn.setProperty("class", "nav-btn")
            btn.setProperty("active", "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(40)
            btn.clicked.connect(lambda checked=False, k=key: self._on_click(k))
            self._buttons[key] = btn
            layout.addWidget(btn)

        layout.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # Version en bas
        self._version_label = QLabel("v1.0.0")
        self._version_label.setStyleSheet("color:#636366; font-size:11px; padding:4px 14px;")
        layout.addWidget(self._version_label)

    def _on_click(self, key: str) -> None:
        self.set_active(key)
        self.page_requested.emit(key)

    def set_active(self, key: str) -> None:
        if self._active_key:
            btn = self._buttons.get(self._active_key)
            if btn:
                btn.setProperty("active", "false")
                btn.style().unpolish(btn)
                btn.style().polish(btn)
        self._active_key = key
        btn = self._buttons.get(key)
        if btn:
            btn.setProperty("active", "true")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def set_version(self, version: str) -> None:
        self._version_label.setText(f"v{version}")

    def set_badge(self, key: str, count: int) -> None:
        """Ajoute un badge numérique sur un item (ex: file d'attente)."""
        btn = self._buttons.get(key)
        if not btn:
            return
        for _, icon, label in SIDEBAR_ITEMS:
            if key == _:
                text = f"  {icon}  {label}"
                if count > 0:
                    text += f"  [{count}]"
                btn.setText(text)
                break
