"""
Vue Import médias — drag & drop, scan, liste des fichiers, file d'attente.
"""
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QFileDialog, QProgressBar, QScrollArea,
    QListWidget, QListWidgetItem, QSizePolicy, QSplitter,
    QAbstractItemView, QMenu
)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QSize, QTimer
from PySide6.QtGui import QPixmap, QDragEnterEvent, QDropEvent, QColor, QFont

from media.media_model import MediaFile, MediaStatus
from logs.logger import get_logger

log = get_logger("ui.import")

STATUS_COLORS = {
    MediaStatus.READY:      ("#dcfce7", "#16a34a"),
    MediaStatus.DUPLICATE:  ("#fef9c3", "#ca8a04"),
    MediaStatus.FAILED:     ("#fee2e2", "#dc2626"),
    MediaStatus.UPLOADING:  ("#dbeafe", "#2563eb"),
    MediaStatus.UPLOADED:   ("#f0fdf4", "#15803d"),
    MediaStatus.SCANNING:   ("#f1f5f9", "#64748b"),
}
STATUS_LABELS = {
    MediaStatus.READY:      "Prêt",
    MediaStatus.DUPLICATE:  "Doublon",
    MediaStatus.FAILED:     "Erreur",
    MediaStatus.UPLOADING:  "Upload…",
    MediaStatus.UPLOADED:   "Uploadé ✓",
    MediaStatus.SCANNING:   "Scan…",
}


class ScanWorker(QThread):
    progress    = Signal(int, int, str)       # current, total, filename
    file_found  = Signal(object)              # MediaFile
    finished    = Signal(list)                # list[MediaFile]

    def __init__(self, root: str, auto_queue: bool = False):
        super().__init__()
        self.root = root
        self.auto_queue = auto_queue
        self._results: list[MediaFile] = []

    def run(self):
        from media.scanner import scan_and_process

        def cb(cur, tot, fname):
            self.progress.emit(cur, tot, fname)

        results = scan_and_process(self.root, progress_cb=cb, auto_queue=self.auto_queue)
        for m in results:
            self.file_found.emit(m)
        self.finished.emit(results)


class DropZone(QFrame):
    """Zone de drop avec style."""
    files_dropped = Signal(list)  # list[str]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._build()

    def _build(self):
        self.setMinimumHeight(140)
        self._update_style(False)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon = QLabel("📁")
        self._icon.setStyleSheet("font-size: 36px;")
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._label = QLabel("Glissez des fichiers ou un dossier ici")
        self._label.setStyleSheet("font-size: 14px; font-weight: 600; color: #374151;")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._sub = QLabel("Photos · Vidéos · FIT · GPX — ou cliquez pour parcourir")
        self._sub.setStyleSheet("font-size: 12px; color: #9ca3af;")
        self._sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self._icon)
        layout.addWidget(self._label)
        layout.addWidget(self._sub)

    def _update_style(self, active: bool):
        color = "#f97316" if active else "#d1d5db"
        bg    = "#fff7ed" if active else "#f8fafc"
        self.setStyleSheet(f"""
            QFrame {{ background: {bg}; border: 2px dashed {color};
                     border-radius: 14px; }}
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            self._update_style(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._update_style(False)

    def dropEvent(self, event: QDropEvent):
        self._update_style(False)
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        if paths:
            self.files_dropped.emit(paths)
        event.acceptProposedAction()

    def mousePressEvent(self, event):
        self.files_dropped.emit([])   # signal vide → ouvre le dialog


class MediaItemWidget(QWidget):
    """Widget d'un fichier dans la liste."""

    def __init__(self, media: MediaFile, parent=None):
        super().__init__(parent)
        self.media = media
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        # Miniature
        self._thumb = QLabel()
        self._thumb.setFixedSize(64, 48)
        self._thumb.setStyleSheet("background: #e5e7eb; border-radius: 6px;")
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_thumb()
        layout.addWidget(self._thumb)

        # Infos
        info = QVBoxLayout()
        info.setSpacing(2)

        self._name_lbl = QLabel(self.media.original_name or Path(self.media.local_path).name)
        self._name_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #1f2937;")
        self._name_lbl.setMaximumWidth(340)

        meta_parts = []
        if self.media.size_bytes:
            meta_parts.append(_fmt_size(self.media.size_bytes))
        if self.media.captured_at:
            meta_parts.append(self.media.captured_at[:10])
        if self.media.file_type:
            meta_parts.append(self.media.file_type.upper())

        self._meta_lbl = QLabel(" · ".join(meta_parts) or "—")
        self._meta_lbl.setStyleSheet("font-size: 11px; color: #6b7280;")

        info.addWidget(self._name_lbl)
        info.addWidget(self._meta_lbl)
        layout.addLayout(info)
        layout.addStretch()

        # Badge statut
        self._status_badge = QLabel()
        self._update_status_badge()
        layout.addWidget(self._status_badge)

    def _load_thumb(self):
        if self.media.thumbnail_path and Path(self.media.thumbnail_path).exists():
            pix = QPixmap(self.media.thumbnail_path).scaled(
                64, 48,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._thumb.setPixmap(pix)
        else:
            icon = "🎬" if self.media.file_type == "video" else "📷"
            self._thumb.setText(icon)
            self._thumb.setStyleSheet("font-size: 22px; background: #e5e7eb; border-radius: 6px;")

    def _update_status_badge(self):
        status = self.media.status
        bg, color = STATUS_COLORS.get(status, ("#f1f5f9", "#64748b"))
        label = STATUS_LABELS.get(status, status)
        self._status_badge.setText(label)
        self._status_badge.setStyleSheet(f"""
            QLabel {{ background: {bg}; color: {color}; border-radius: 6px;
                     padding: 3px 8px; font-size: 11px; font-weight: 700; }}
        """)

    def refresh(self):
        self._update_status_badge()
        self._load_thumb()


class MediaImportView(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results: list[MediaFile] = []
        self._scan_worker: ScanWorker | None = None
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("background: #f5f5f7;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        # Titre + boutons
        header = QHBoxLayout()
        title = QLabel("Import médias")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #1a1d27;")
        header.addWidget(title)
        header.addStretch()

        self._btn_queue_all = QPushButton("📤 Tout mettre en file")
        self._btn_queue_all.setStyleSheet(self._btn_style("#f97316"))
        self._btn_queue_all.setEnabled(False)
        self._btn_queue_all.clicked.connect(self._on_queue_all)
        header.addWidget(self._btn_queue_all)

        self._btn_clear = QPushButton("🗑 Effacer")
        self._btn_clear.setStyleSheet(self._btn_style("#6b7280"))
        self._btn_clear.setEnabled(False)
        self._btn_clear.clicked.connect(self._on_clear)
        header.addWidget(self._btn_clear)

        layout.addLayout(header)

        # Drop zone
        self._drop_zone = DropZone()
        self._drop_zone.files_dropped.connect(self._on_drop)
        layout.addWidget(self._drop_zone)

        # Barre de progression (cachée par défaut)
        self._progress = QProgressBar()
        self._progress.setStyleSheet("""
            QProgressBar { background: #e5e7eb; border-radius: 6px; height: 8px; border: none; text-align: center; }
            QProgressBar::chunk { background: #f97316; border-radius: 6px; }
        """)
        self._progress.setVisible(False)
        self._progress.setTextVisible(False)
        layout.addWidget(self._progress)

        self._progress_label = QLabel("")
        self._progress_label.setStyleSheet("font-size: 12px; color: #6b7280; text-align: center;")
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_label.setVisible(False)
        layout.addWidget(self._progress_label)

        # Résumé
        self._summary = QLabel("")
        self._summary.setStyleSheet("font-size: 13px; color: #374151; font-weight: 500;")
        layout.addWidget(self._summary)

        # Liste des fichiers
        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget { background: #ffffff; border-radius: 12px; border: 1px solid #e5e7eb; }
            QListWidget::item { border-bottom: 1px solid #f1f5f9; padding: 4px; }
            QListWidget::item:selected { background: #fff7ed; }
        """)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._list)

    def _on_drop(self, paths: list[str]):
        if not paths:
            # Ouvrir dialog dossier
            folder = QFileDialog.getExistingDirectory(self, "Sélectionner un dossier")
            if folder:
                paths = [folder]
            else:
                return

        # Prendre le premier path (ou scanner tous)
        root = paths[0]
        self._start_scan(root)

    def _start_scan(self, root: str):
        if self._scan_worker and self._scan_worker.isRunning():
            return

        self._results.clear()
        self._list.clear()
        self._summary.setText(f"Scan de {root}…")
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._progress_label.setVisible(True)
        self._btn_queue_all.setEnabled(False)
        self._btn_clear.setEnabled(False)

        self._scan_worker = ScanWorker(root)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.file_found.connect(self._on_file_found)
        self._scan_worker.finished.connect(self._on_scan_done)
        self._scan_worker.start()

    @Slot(int, int, str)
    def _on_scan_progress(self, cur: int, total: int, fname: str):
        if total > 0:
            self._progress.setMaximum(total)
            self._progress.setValue(cur)
        self._progress_label.setText(f"Scan… {fname}")

    @Slot(object)
    def _on_file_found(self, media: MediaFile):
        self._results.append(media)
        item = QListWidgetItem(self._list)
        widget = MediaItemWidget(media)
        item.setSizeHint(QSize(0, 72))
        self._list.addItem(item)
        self._list.setItemWidget(item, widget)

    @Slot(list)
    def _on_scan_done(self, results: list):
        self._progress.setVisible(False)
        self._progress_label.setVisible(False)

        total   = len(results)
        ready   = sum(1 for m in results if m.status == MediaStatus.READY)
        dups    = sum(1 for m in results if m.status == MediaStatus.DUPLICATE)
        errors  = sum(1 for m in results if m.status == MediaStatus.FAILED)

        parts = [f"{total} fichier(s) trouvé(s)"]
        if ready:
            parts.append(f"<span style='color:#16a34a'>{ready} prêts</span>")
        if dups:
            parts.append(f"<span style='color:#ca8a04'>{dups} doublons</span>")
        if errors:
            parts.append(f"<span style='color:#dc2626'>{errors} erreurs</span>")

        self._summary.setText(" · ".join(parts))
        self._summary.setTextFormat(Qt.TextFormat.RichText)
        self._btn_queue_all.setEnabled(ready > 0)
        self._btn_clear.setEnabled(True)

    def _on_queue_all(self):
        from sync.upload_manager import get_upload_manager
        mgr = get_upload_manager()
        count = 0
        for media in self._results:
            if media.status == MediaStatus.READY and media.db_id:
                mgr.add_to_queue(media.db_id)
                media.status = MediaStatus.UPLOADING
                count += 1
        # Rafraîchir les badges
        for i in range(self._list.count()):
            widget = self._list.itemWidget(self._list.item(i))
            if widget:
                widget.refresh()
        mgr.start()
        self._summary.setText(f"✅ {count} fichier(s) ajouté(s) à la file d'upload")
        self._btn_queue_all.setEnabled(False)

    def _on_clear(self):
        self._results.clear()
        self._list.clear()
        self._summary.setText("")
        self._btn_queue_all.setEnabled(False)
        self._btn_clear.setEnabled(False)

    def _on_context_menu(self, pos):
        item = self._list.itemAt(pos)
        if not item:
            return
        idx = self._list.row(item)
        if idx >= len(self._results):
            return
        media = self._results[idx]

        menu = QMenu(self)
        if media.status == MediaStatus.READY and media.db_id:
            act_queue = menu.addAction("📤 Ajouter à la file d'upload")
            act_queue.triggered.connect(lambda: self._queue_single(media))
        act_reveal = menu.addAction("📂 Afficher dans Finder")
        act_reveal.triggered.connect(lambda: self._reveal_in_finder(media.local_path))
        act_ignore = menu.addAction("🚫 Ignorer")
        act_ignore.triggered.connect(lambda: self._ignore_media(idx, media))
        menu.exec(self._list.mapToGlobal(pos))

    def _queue_single(self, media: MediaFile):
        from sync.upload_manager import get_upload_manager
        mgr = get_upload_manager()
        mgr.add_to_queue(media.db_id)
        media.status = MediaStatus.UPLOADING
        mgr.start()
        # Rafraîchir le widget
        for i in range(self._list.count()):
            w = self._list.itemWidget(self._list.item(i))
            if w and w.media is media:
                w.refresh()
                break

    def _reveal_in_finder(self, path: str):
        import subprocess
        subprocess.Popen(["open", "-R", path])

    def _ignore_media(self, idx: int, media: MediaFile):
        if media.db_id:
            from storage.local_db import db
            db().execute(
                "UPDATE media_files SET status='ignored' WHERE id=?", (media.db_id,)
            )
            db().commit()
        media.status = MediaStatus.IGNORED
        w = self._list.itemWidget(self._list.item(idx))
        if w:
            w.refresh()

    def _btn_style(self, color: str) -> str:
        return f"""
            QPushButton {{ background: {color}; color: white; border: none;
                           border-radius: 8px; padding: 8px 16px; font-weight: 600; font-size: 13px; }}
            QPushButton:hover {{ opacity: 0.9; }}
            QPushButton:disabled {{ background: #d1d5db; color: #9ca3af; }}
        """


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 ** 2:
        return f"{n/1024:.0f}KB"
    if n < 1024 ** 3:
        return f"{n/1024**2:.1f}MB"
    return f"{n/1024**3:.2f}GB"
