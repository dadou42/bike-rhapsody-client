"""
Vue Logs — affiche le contenu du fichier de log en temps réel.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QFileDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from logs.logger import get_log_file_path


class LogsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(3000)

    def _build_ui(self):
        self.setStyleSheet("background: #f5f5f7;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        # Header
        header = QHBoxLayout()
        title = QLabel("Logs")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #1a1d27;")
        header.addWidget(title)
        header.addStretch()

        btn_export = QPushButton("📤 Exporter")
        btn_export.setStyleSheet("""
            QPushButton { background: #3b82f6; color: white; border: none;
                          border-radius: 8px; padding: 7px 16px; font-weight: 600; }
            QPushButton:hover { background: #2563eb; }
        """)
        btn_export.clicked.connect(self._on_export)

        btn_clear = QPushButton("🗑 Effacer l'affichage")
        btn_clear.setStyleSheet("""
            QPushButton { background: #e5e7eb; color: #374151; border: none;
                          border-radius: 8px; padding: 7px 16px; font-weight: 600; }
            QPushButton:hover { background: #d1d5db; }
        """)
        btn_clear.clicked.connect(lambda: self._text.clear())

        header.addWidget(btn_export)
        header.addWidget(btn_clear)
        layout.addLayout(header)

        # Zone texte
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(QFont("Menlo", 11))
        self._text.setStyleSheet("""
            QTextEdit { background: #1c1c1e; color: #e2e8f0; border-radius: 10px;
                        border: none; padding: 12px; }
        """)
        layout.addWidget(self._text)

        self._refresh()

    def _refresh(self):
        log_file = get_log_file_path()
        if not log_file.exists():
            return
        try:
            content = log_file.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            # Garder les 500 dernières lignes
            visible = "\n".join(lines[-500:])
            if visible != self._text.toPlainText():
                self._text.setPlainText(visible)
                # Scroll vers le bas
                bar = self._text.verticalScrollBar()
                bar.setValue(bar.maximum())
        except Exception:
            pass

    def _on_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter les logs", "bike_rhapsody_client.log", "Log files (*.log)"
        )
        if path:
            import shutil
            shutil.copy(get_log_file_path(), path)
