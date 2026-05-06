"""
Vue File d'attente — affichage en direct des uploads, pause/reprise/retry.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QProgressBar, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSizePolicy
)
from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QColor

from logs.logger import get_logger

log = get_logger("ui.queue")

STATUS_STYLE = {
    "pending":   ("En attente",  "#f1f5f9", "#64748b"),
    "uploading": ("Upload…",     "#dbeafe", "#2563eb"),
    "retrying":  ("Retry…",      "#fef9c3", "#ca8a04"),
    "done":      ("Uploadé ✓",   "#dcfce7", "#16a34a"),
    "failed":    ("Erreur",      "#fee2e2", "#dc2626"),
}


class QueueView(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = None
        self._build_ui()
        # Connecter le manager une fois disponible
        QTimer.singleShot(500, self._connect_manager)
        # Rafraîchit la table toutes les 3s
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_table)
        self._timer.start(3000)

    def _build_ui(self):
        self.setStyleSheet("background: #f5f5f7;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title = QLabel("File d'attente")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #1a1d27;")
        header.addWidget(title)
        header.addStretch()

        self._btn_pause = QPushButton("⏸ Pause")
        self._btn_pause.setStyleSheet(self._btn("#f59e0b"))
        self._btn_pause.clicked.connect(self._on_pause_resume)
        header.addWidget(self._btn_pause)

        self._btn_retry = QPushButton("🔄 Retry erreurs")
        self._btn_retry.setStyleSheet(self._btn("#3b82f6"))
        self._btn_retry.clicked.connect(self._on_retry_all)
        header.addWidget(self._btn_retry)

        layout.addLayout(header)

        # Stats cards
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)
        self._card_pending  = self._make_stat_card("En attente", "0", "#f59e0b")
        self._card_uploading = self._make_stat_card("En cours",  "0", "#3b82f6")
        self._card_done     = self._make_stat_card("Uploadés",   "0", "#22c55e")
        self._card_errors   = self._make_stat_card("Erreurs",    "0", "#ef4444")
        stats_row.addWidget(self._card_pending)
        stats_row.addWidget(self._card_uploading)
        stats_row.addWidget(self._card_done)
        stats_row.addWidget(self._card_errors)
        layout.addLayout(stats_row)

        # Upload courant
        self._current_label = QLabel("Aucun upload en cours")
        self._current_label.setStyleSheet("font-size: 13px; color: #374151;")
        self._progress = QProgressBar()
        self._progress.setStyleSheet("""
            QProgressBar { background: #e5e7eb; border-radius: 6px; height: 10px; border: none; }
            QProgressBar::chunk { background: #f97316; border-radius: 6px; }
        """)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        layout.addWidget(self._current_label)
        layout.addWidget(self._progress)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Fichier", "Taille", "Statut", "Tentatives", "Dernière erreur"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet("""
            QTableWidget { background: #ffffff; border-radius: 12px; border: 1px solid #e5e7eb;
                           gridline-color: #f1f5f9; }
            QTableWidget::item { padding: 6px; }
            QHeaderView::section { background: #f8fafc; font-weight: 700; font-size: 12px;
                                   border: none; border-bottom: 1px solid #e5e7eb; padding: 6px; }
        """)
        layout.addWidget(self._table)
        self._refresh_table()

    def _connect_manager(self):
        try:
            from sync.upload_manager import get_upload_manager
            self._manager = get_upload_manager()
            self._manager.file_started.connect(self._on_file_started)
            self._manager.file_progress.connect(self._on_file_progress)
            self._manager.file_done.connect(self._on_file_done)
            self._manager.file_failed.connect(self._on_file_failed)
        except Exception as e:
            log.debug("Manager not ready yet: %s", e)

    @Slot(int, str)
    def _on_file_started(self, media_id: int, filename: str):
        self._current_label.setText(f"⬆️  {filename}")
        self._progress.setValue(0)

    @Slot(int, int, int)
    def _on_file_progress(self, media_id: int, done: int, total: int):
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(done)
            pct = int(done / total * 100)
            self._current_label.setText(
                f"⬆️  {pct}% — {_fmt_size(done)} / {_fmt_size(total)}"
            )

    @Slot(int, str)
    def _on_file_done(self, media_id: int, server_id: str):
        self._current_label.setText("✅ Upload terminé")
        self._progress.setValue(0)
        self._refresh_table()

    @Slot(int, str, str)
    def _on_file_failed(self, media_id: int, error: str, retry_label: str):
        self._current_label.setText(f"⚠️ Erreur — retry dans {retry_label}")
        self._refresh_table()

    def _refresh_table(self):
        from storage.local_db import db
        try:
            rows = db().execute(
                """SELECT q.id, q.status, q.retry_count, q.last_error, q.next_retry_at,
                          m.original_name, m.size_bytes
                   FROM upload_queue q
                   JOIN media_files m ON m.id = q.media_id
                   ORDER BY q.created_at DESC
                   LIMIT 200"""
            ).fetchall()
        except Exception:
            return

        pending = uploading = done = errors = 0
        self._table.setRowCount(len(rows))

        for i, row in enumerate(rows):
            status = row["status"]
            if status in ("pending", "retrying"):
                pending += 1
            elif status == "uploading":
                uploading += 1
            elif status == "done":
                done += 1
            elif status == "failed":
                errors += 1

            bg_hex, color_hex, label = STATUS_STYLE.get(status, ("", "#6b7280", status))

            name_item = QTableWidgetItem(row["original_name"] or "—")
            size_item = QTableWidgetItem(_fmt_size(row["size_bytes"] or 0))
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            status_item = QTableWidgetItem(label)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if bg_hex:
                status_item.setBackground(QColor(bg_hex))
            status_item.setForeground(QColor(color_hex))

            retry_item = QTableWidgetItem(str(row["retry_count"] or 0))
            retry_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            error_item = QTableWidgetItem(row["last_error"] or "")

            self._table.setItem(i, 0, name_item)
            self._table.setItem(i, 1, size_item)
            self._table.setItem(i, 2, status_item)
            self._table.setItem(i, 3, retry_item)
            self._table.setItem(i, 4, error_item)

        self._set_stat_card(self._card_pending, str(pending))
        self._set_stat_card(self._card_uploading, str(uploading))
        self._set_stat_card(self._card_done, str(done))
        self._set_stat_card(self._card_errors, str(errors))

    def _on_pause_resume(self):
        if not self._manager:
            return
        if self._manager.is_paused():
            self._manager.resume()
            self._btn_pause.setText("⏸ Pause")
        else:
            self._manager.pause()
            self._btn_pause.setText("▶ Reprendre")

    def _on_retry_all(self):
        if self._manager:
            count = self._manager.retry_failed()
            self._manager.start()
            self._current_label.setText(f"🔄 {count} upload(s) relancé(s)")
            self._refresh_table()

    def _make_stat_card(self, label: str, value: str, color: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame { background: #ffffff; border-radius: 10px; border: 1px solid #e2e8f0; }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        lbl = QLabel(label)
        lbl.setStyleSheet("font-size: 11px; color: #6b7280;")
        val = QLabel(value)
        val.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {color};")
        val.setObjectName("stat_val")
        layout.addWidget(lbl)
        layout.addWidget(val)
        return frame

    def _set_stat_card(self, frame: QFrame, value: str):
        lbl = frame.findChild(QLabel, "stat_val")
        if lbl:
            lbl.setText(value)

    def _btn(self, color: str) -> str:
        return f"""
            QPushButton {{ background: {color}; color: white; border: none;
                           border-radius: 8px; padding: 8px 16px; font-weight: 600; }}
            QPushButton:hover {{ opacity: 0.9; }}
        """


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 ** 2:
        return f"{n/1024:.0f}KB"
    if n < 1024 ** 3:
        return f"{n/1024**2:.1f}MB"
    return f"{n/1024**3:.2f}GB"
