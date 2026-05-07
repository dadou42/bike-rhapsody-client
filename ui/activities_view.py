"""
Vue Activités — Phase 3 : matching orphan_media ↔ activités.

Affiche :
  • Bandeau "X médias orphelins / Y matchés" avec bouton "🔗 Matcher auto"
  • Liste activités (date, nom, distance, durée, nb médias liés)
  • Panneau droite : médias orphelins glissables vers une activité

Drag & drop : on drag un orphan_media (par son media_id) vers une carte
activité → POST /api/media/orphans/{id}/link?activity_id=X
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, Slot, QMimeData, QPoint
from PySide6.QtGui import QDrag, QPixmap, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QListWidget, QListWidgetItem, QSplitter, QScrollArea,
    QAbstractItemView, QSizePolicy, QSpinBox, QMessageBox, QMenu,
)

from logs.logger import get_logger

log = get_logger("ui.activities")


# ── Workers ──────────────────────────────────────────────────────────────────

class _Loader(QThread):
    done = Signal(object)   # dict {activities, orphans}

    def run(self):
        from api.matching_api import list_activities, list_orphans
        try:
            acts = list_activities(limit=80)
            orphs = list_orphans(only_unmatched=True, limit=300)
            self.done.emit({"activities": acts, "orphans": orphs})
        except Exception as e:
            log.error("Loader failed: %s", e)
            self.done.emit({"activities": [], "orphans": [], "error": str(e)})


class _MatchWorker(QThread):
    done = Signal(object)   # dict result

    def __init__(self, tolerance_minutes: int, dry_run: bool):
        super().__init__()
        self.tolerance = tolerance_minutes
        self.dry_run = dry_run

    def run(self):
        from api.matching_api import match_orphans
        try:
            res = match_orphans(self.tolerance, self.dry_run)
            self.done.emit(res)
        except Exception as e:
            log.error("MatchWorker failed: %s", e)
            self.done.emit({"error": str(e), "matched": 0})


# ── Helpers UI ───────────────────────────────────────────────────────────────

def _fmt_distance(meters: Optional[float]) -> str:
    if not meters:
        return "—"
    km = meters / 1000.0
    return f"{km:.1f} km"


def _fmt_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "—"
    m = int(seconds) // 60
    if m < 60:
        return f"{m} min"
    return f"{m // 60}h{m % 60:02d}"


def _fmt_date(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        s = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt.strftime("%d %b %Y · %H:%M")
    except Exception:
        return iso[:16]


# ── Carte activité (accepte le drop) ─────────────────────────────────────────

class ActivityCard(QFrame):
    media_dropped = Signal(int, int)   # (media_id, activity_id)

    def __init__(self, activity: dict, parent=None):
        super().__init__(parent)
        self.activity = activity
        self.setAcceptDrops(True)
        self.setObjectName("activity_card")
        self._build()
        self._set_drop_state(False)

    def _build(self):
        self.setMinimumHeight(78)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(12)

        # Colonne infos
        col = QVBoxLayout()
        col.setSpacing(2)

        name = self.activity.get("name") or "Activité sans nom"
        self._name_lbl = QLabel(name)
        self._name_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #1f2937;")
        col.addWidget(self._name_lbl)

        meta_parts = [
            _fmt_date(self.activity.get("start_date")),
            _fmt_distance(self.activity.get("distance")),
            _fmt_duration(self.activity.get("elapsed_time")),
        ]
        city = self.activity.get("start_city")
        if city:
            meta_parts.append(f"📍 {city}")
        self._meta_lbl = QLabel(" · ".join(meta_parts))
        self._meta_lbl.setStyleSheet("font-size: 11px; color: #6b7280;")
        col.addWidget(self._meta_lbl)

        outer.addLayout(col, stretch=1)

        # Compteur de médias liés
        cnt = int(self.activity.get("media_count") or 0)
        self._badge = QLabel(f"📷 {cnt}")
        self._badge.setStyleSheet(
            "background:#dcfce7; color:#16a34a; border-radius:6px; "
            "padding:4px 10px; font-size:12px; font-weight:700;"
            if cnt else
            "background:#f1f5f9; color:#94a3b8; border-radius:6px; "
            "padding:4px 10px; font-size:12px; font-weight:600;"
        )
        outer.addWidget(self._badge)

    def _set_drop_state(self, active: bool):
        if active:
            self.setStyleSheet("""
                QFrame#activity_card {
                    background: #fff7ed; border: 2px dashed #f97316; border-radius: 12px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#activity_card {
                    background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px;
                }
                QFrame#activity_card:hover {
                    border-color: #f97316;
                }
            """)

    def update_count(self, delta: int):
        cnt = int(self.activity.get("media_count") or 0) + delta
        self.activity["media_count"] = cnt
        self._badge.setText(f"📷 {cnt}")
        self._badge.setStyleSheet(
            "background:#dcfce7; color:#16a34a; border-radius:6px; "
            "padding:4px 10px; font-size:12px; font-weight:700;"
            if cnt else
            "background:#f1f5f9; color:#94a3b8; border-radius:6px; "
            "padding:4px 10px; font-size:12px; font-weight:600;"
        )

    # ── Drag & drop ──────────────────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-orphan-media-id"):
            self._set_drop_state(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._set_drop_state(False)

    def dropEvent(self, event):
        self._set_drop_state(False)
        data = event.mimeData().data("application/x-orphan-media-id")
        try:
            media_id = int(bytes(data).decode("utf-8"))
            self.media_dropped.emit(media_id, int(self.activity["id"]))
            event.acceptProposedAction()
        except Exception as e:
            log.warning("Drop parse failed: %s", e)


# ── Liste orphelins (drag source) ───────────────────────────────────────────

class OrphanListWidget(QListWidget):
    """Liste des orphan_media — items draggables vers une ActivityCard."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setStyleSheet("""
            QListWidget { background:#fff; border:1px solid #e5e7eb; border-radius:10px; }
            QListWidget::item { padding:10px; border-bottom:1px solid #f1f5f9; }
            QListWidget::item:selected { background:#fff7ed; }
        """)

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if not item:
            return
        media_id = item.data(Qt.ItemDataRole.UserRole)
        if media_id is None:
            return

        mime = QMimeData()
        mime.setData("application/x-orphan-media-id", str(int(media_id)).encode("utf-8"))
        mime.setText(item.text())

        drag = QDrag(self)
        drag.setMimeData(mime)

        # Pixmap simple (texte du libellé)
        pix = QPixmap(220, 32)
        pix.fill(QColor("#fff7ed"))
        drag.setPixmap(pix)
        drag.setHotSpot(QPoint(10, 10))

        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)


# ── Vue principale ──────────────────────────────────────────────────────────

class ActivitiesView(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loader: Optional[_Loader] = None
        self._matcher: Optional[_MatchWorker] = None
        self._activity_cards: dict[int, ActivityCard] = {}
        self._build_ui()

    # ── UI build ────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.setStyleSheet("background:#f5f5f7;")
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(14)

        # Header
        header = QHBoxLayout()
        title = QLabel("Activités & matching médias")
        title.setStyleSheet("font-size:22px; font-weight:700; color:#1a1d27;")
        header.addWidget(title)
        header.addStretch()

        self._btn_refresh = QPushButton("↻ Actualiser")
        self._btn_refresh.setStyleSheet(self._btn("#64748b"))
        self._btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self._btn_refresh)

        root.addLayout(header)

        # Bandeau matching
        match_box = QFrame()
        match_box.setStyleSheet(
            "QFrame { background:#ffffff; border:1px solid #e5e7eb; border-radius:12px; }"
        )
        mb = QHBoxLayout(match_box)
        mb.setContentsMargins(16, 12, 16, 12)
        mb.setSpacing(12)

        self._summary_lbl = QLabel("…")
        self._summary_lbl.setStyleSheet("font-size:13px; color:#374151; font-weight:600;")
        mb.addWidget(self._summary_lbl)
        mb.addStretch()

        tol_lbl = QLabel("Tolérance ±")
        tol_lbl.setStyleSheet("font-size:12px; color:#6b7280;")
        mb.addWidget(tol_lbl)

        self._spin_tol = QSpinBox()
        self._spin_tol.setRange(0, 240)
        self._spin_tol.setValue(30)
        self._spin_tol.setSuffix(" min")
        self._spin_tol.setStyleSheet(
            "QSpinBox { background:#f8fafc; border:1px solid #d1d5db; "
            "border-radius:6px; padding:4px 6px; font-size:12px; }"
        )
        mb.addWidget(self._spin_tol)

        self._btn_preview = QPushButton("👁 Aperçu")
        self._btn_preview.setStyleSheet(self._btn("#0ea5e9"))
        self._btn_preview.setToolTip("Simuler le matching sans appliquer")
        self._btn_preview.clicked.connect(lambda: self._do_match(dry_run=True))
        mb.addWidget(self._btn_preview)

        self._btn_match = QPushButton("🔗 Matcher auto")
        self._btn_match.setStyleSheet(self._btn("#f97316"))
        self._btn_match.clicked.connect(lambda: self._do_match(dry_run=False))
        mb.addWidget(self._btn_match)

        root.addWidget(match_box)

        # Splitter : activités | orphelins
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Activités (gauche) ───────────────────────────────────────────────
        left = QFrame()
        left.setStyleSheet("background:#f5f5f7;")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(8)

        lv.addWidget(self._section_label("Activités"))

        self._activities_scroll = QScrollArea()
        self._activities_scroll.setWidgetResizable(True)
        self._activities_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._activities_scroll.setStyleSheet("background:transparent;")
        self._activities_container = QWidget()
        self._activities_container.setStyleSheet("background:transparent;")
        self._activities_layout = QVBoxLayout(self._activities_container)
        self._activities_layout.setContentsMargins(0, 0, 0, 0)
        self._activities_layout.setSpacing(8)
        self._activities_layout.addStretch()
        self._activities_scroll.setWidget(self._activities_container)
        lv.addWidget(self._activities_scroll)

        splitter.addWidget(left)

        # ── Orphelins (droite) ───────────────────────────────────────────────
        right = QFrame()
        right.setStyleSheet("background:#f5f5f7;")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)

        orphans_header = QHBoxLayout()
        orphans_header.addWidget(self._section_label("Médias orphelins"))
        hint = QLabel("(glisse vers une activité pour lier)")
        hint.setStyleSheet("font-size:11px; color:#9ca3af;")
        orphans_header.addWidget(hint)
        orphans_header.addStretch()
        rv.addLayout(orphans_header)

        self._orphan_list = OrphanListWidget()
        self._orphan_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._orphan_list.customContextMenuRequested.connect(self._on_orphan_context_menu)
        rv.addWidget(self._orphan_list)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, stretch=1)

        # Lazy-load au premier showEvent
        self._loaded = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            self.refresh()

    # ── Helpers UI ──────────────────────────────────────────────────────────

    def _section_label(self, txt: str) -> QLabel:
        lbl = QLabel(txt)
        lbl.setStyleSheet("font-size:13px; font-weight:700; color:#374151; padding:2px 4px;")
        return lbl

    def _btn(self, color: str) -> str:
        return f"""
            QPushButton {{ background:{color}; color:white; border:none;
                           border-radius:8px; padding:6px 14px; font-weight:600; font-size:12px; }}
            QPushButton:hover {{ opacity:0.9; }}
            QPushButton:disabled {{ background:#d1d5db; color:#9ca3af; }}
        """

    # ── Loading ─────────────────────────────────────────────────────────────

    def refresh(self):
        self._summary_lbl.setText("Chargement…")
        self._btn_refresh.setEnabled(False)
        self._btn_match.setEnabled(False)
        self._btn_preview.setEnabled(False)
        self._loader = _Loader()
        self._loader.done.connect(self._on_loaded)
        self._loader.start()

    @Slot(object)
    def _on_loaded(self, payload: dict):
        self._btn_refresh.setEnabled(True)
        if payload.get("error"):
            self._summary_lbl.setText(f"❌ {payload['error']}")
            return

        activities = payload.get("activities", []) or []
        orphans    = payload.get("orphans", []) or []

        # Activités
        # On nettoie les anciens cards
        while self._activities_layout.count() > 0:
            item = self._activities_layout.takeAt(0)
            w = item.widget() if item else None
            if w:
                w.deleteLater()
        self._activity_cards.clear()

        if not activities:
            empty = QLabel("Aucune activité — synchronise depuis Strava côté webapp.")
            empty.setStyleSheet("color:#9ca3af; font-size:12px; padding:14px;")
            self._activities_layout.addWidget(empty)
        else:
            for act in activities:
                card = ActivityCard(act)
                card.media_dropped.connect(self._on_media_dropped)
                self._activity_cards[int(act["id"])] = card
                self._activities_layout.addWidget(card)
        self._activities_layout.addStretch()

        # Orphelins
        self._orphan_list.clear()
        for orph in orphans:
            label_parts = [orph.get("original_name") or f"#{orph['id']}"]
            if orph.get("captured_at"):
                label_parts.append(str(orph["captured_at"])[:16].replace("T", " "))
            if orph.get("file_type"):
                label_parts.append(str(orph["file_type"]).upper())
            if orph.get("gps_lat") and orph.get("gps_lon"):
                label_parts.append(f"🛰 {float(orph['gps_lat']):.4f},{float(orph['gps_lon']):.4f}")
            item = QListWidgetItem(" · ".join(label_parts))
            item.setData(Qt.ItemDataRole.UserRole, int(orph["id"]))
            self._orphan_list.addItem(item)

        # Résumé
        n_act = len(activities)
        n_orph = len(orphans)
        n_matched = sum(int(a.get("media_count") or 0) for a in activities)
        self._summary_lbl.setText(
            f"📷 <b>{n_orph}</b> orphelin(s) à matcher  ·  "
            f"🔗 <b>{n_matched}</b> média(s) déjà liés sur <b>{n_act}</b> activité(s)"
        )
        self._summary_lbl.setTextFormat(Qt.TextFormat.RichText)

        self._btn_match.setEnabled(n_orph > 0 and n_act > 0)
        self._btn_preview.setEnabled(n_orph > 0 and n_act > 0)

    # ── Matching ────────────────────────────────────────────────────────────

    def _do_match(self, dry_run: bool):
        tol = self._spin_tol.value()
        self._btn_match.setEnabled(False)
        self._btn_preview.setEnabled(False)
        self._summary_lbl.setText(
            f"{'👁 Simulation' if dry_run else '🔗 Matching'} en cours (±{tol} min)…"
        )
        self._matcher = _MatchWorker(tol, dry_run)
        self._matcher.done.connect(self._on_match_done)
        self._matcher.start()

    @Slot(object)
    def _on_match_done(self, result: dict):
        self._btn_match.setEnabled(True)
        self._btn_preview.setEnabled(True)
        if result.get("error"):
            QMessageBox.warning(self, "Matching", f"Erreur : {result['error']}")
            return

        matched = result.get("matched", 0)
        candidates = result.get("candidates", 0)
        dry = result.get("dry_run", False)
        details = result.get("details", []) or []

        if dry:
            preview = "\n".join(
                f"  • {d.get('name')} → {d.get('activity_name')}" for d in details[:15]
            )
            extra = f"\n  …et {len(details)-15} autres" if len(details) > 15 else ""
            QMessageBox.information(
                self,
                "Aperçu du matching",
                f"{matched} média(s) seraient liés sur {candidates} candidats "
                f"(tolérance ±{result.get('tolerance_minutes')} min).\n\n"
                f"{preview}{extra}\n\n"
                "Clique '🔗 Matcher auto' pour appliquer.",
            )
            self._summary_lbl.setText(
                f"👁 Simulation : {matched}/{candidates} matchables"
            )
        else:
            QMessageBox.information(
                self,
                "Matching terminé",
                f"✅ {matched} média(s) liés sur {candidates} candidats.\n"
                f"({result.get('activities_scanned')} activités scannées, ±{result.get('tolerance_minutes')} min)",
            )
            self.refresh()

    # ── Drag & drop ─────────────────────────────────────────────────────────

    @Slot(int, int)
    def _on_media_dropped(self, media_id: int, activity_id: int):
        from api.matching_api import link_orphan
        log.info("Linking orphan %d → activity %d", media_id, activity_id)
        if link_orphan(media_id, activity_id):
            # Retirer de la liste orphelins
            for i in range(self._orphan_list.count()):
                item = self._orphan_list.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == media_id:
                    self._orphan_list.takeItem(i)
                    break
            # Bump le compteur de la card
            card = self._activity_cards.get(activity_id)
            if card:
                card.update_count(+1)
            # Rafraîchir le résumé global
            n_orph = self._orphan_list.count()
            n_matched = sum(int(c.activity.get("media_count") or 0)
                            for c in self._activity_cards.values())
            self._summary_lbl.setText(
                f"📷 <b>{n_orph}</b> orphelin(s) · 🔗 <b>{n_matched}</b> média(s) liés"
            )
        else:
            QMessageBox.warning(self, "Liaison", "Échec — vérifie les logs.")

    def _on_orphan_context_menu(self, pos):
        item = self._orphan_list.itemAt(pos)
        if not item:
            return
        media_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        # Sous-menu : lier à une activité (quick-pick)
        link_menu = menu.addMenu("🔗 Lier à une activité…")
        for act_id, card in list(self._activity_cards.items())[:30]:
            name = card.activity.get("name") or f"#{act_id}"
            date = _fmt_date(card.activity.get("start_date"))
            act_menu = link_menu.addAction(f"{date} · {name}")
            act_menu.triggered.connect(
                lambda checked=False, mid=media_id, aid=act_id:
                self._on_media_dropped(mid, aid)
            )
        menu.exec(self._orphan_list.mapToGlobal(pos))
