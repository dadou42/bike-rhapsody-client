"""
Vue placeholder pour les modules non encore développés.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt


class PlaceholderView(QWidget):
    def __init__(self, title: str, icon: str = "🚧", coming: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background: #f5f5f7;")

        ico = QLabel(icon)
        ico.setStyleSheet("font-size: 48px;")
        ico.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl = QLabel(title)
        lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #374151; margin-top: 12px;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub = QLabel(coming or "En cours de développement — Phase 2+")
        sub.setStyleSheet("font-size: 13px; color: #9ca3af; margin-top: 6px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(ico)
        layout.addWidget(lbl)
        layout.addWidget(sub)
