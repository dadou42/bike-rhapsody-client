"""
Vue Paramètres — profils serveur, auth, options générales.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QComboBox, QCheckBox, QMessageBox,
    QScrollArea, QFormLayout, QGroupBox, QInputDialog
)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from app.app_state import get_state
from logs.logger import get_logger

log = get_logger("ui.settings")


class LoginWorker(QThread):
    """Étape 1 : tente le login et émet l'AuthResult complet."""
    finished = Signal(object)   # AuthResult

    def __init__(self, username: str, password: str, profile_name: str):
        super().__init__()
        self.username = username
        self.password = password
        self.profile_name = profile_name

    def run(self):
        from api.auth_api import login
        result = login(self.username, self.password, self.profile_name)
        self.finished.emit(result)


class TwoFAWorker(QThread):
    """Étape 2 : soumet le code TOTP et émet l'AuthResult."""
    finished = Signal(object)   # AuthResult

    def __init__(self, code: str, pending_token: str, profile_name: str):
        super().__init__()
        self.code = code
        self.pending_token = pending_token
        self.profile_name = profile_name

    def run(self):
        from api.auth_api import login_2fa
        result = login_2fa(self.code, self.pending_token, self.profile_name)
        self.finished.emit(result)


class SettingsView(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #f5f5f7; border: none; }")

        content = QWidget()
        content.setStyleSheet("background: #f5f5f7;")
        main = QVBoxLayout(content)
        main.setContentsMargins(28, 28, 28, 28)
        main.setSpacing(20)

        title = QLabel("Paramètres")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #1a1d27;")
        main.addWidget(title)

        # ── Groupe Serveur ────────────────────────────────────────────────────
        server_box = self._make_group("🌐 Connexion serveur")
        server_form = QFormLayout()
        server_form.setSpacing(10)

        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("http://192.168.1.4:8000")
        self._url_input.setStyleSheet(self._input_style())

        self._profile_name_input = QLineEdit()
        self._profile_name_input.setPlaceholderText("NAS local")
        self._profile_name_input.setStyleSheet(self._input_style())

        self._btn_test = QPushButton("Tester la connexion")
        self._btn_test.setStyleSheet(self._btn_style("#3b82f6"))
        self._btn_test.clicked.connect(self._on_test_connection)

        self._btn_save_server = QPushButton("Enregistrer le profil")
        self._btn_save_server.setStyleSheet(self._btn_style("#22c55e"))
        self._btn_save_server.clicked.connect(self._on_save_server)

        self._conn_status = QLabel("")
        self._conn_status.setStyleSheet("font-size: 12px; color: #6b7280;")

        server_form.addRow("Nom du profil :", self._profile_name_input)
        server_form.addRow("URL API :", self._url_input)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._btn_test)
        btn_row.addWidget(self._btn_save_server)
        btn_row.addStretch()

        server_box.layout().addLayout(server_form)
        server_box.layout().addLayout(btn_row)
        server_box.layout().addWidget(self._conn_status)
        main.addWidget(server_box)

        # ── Groupe Authentification ───────────────────────────────────────────
        auth_box = self._make_group("🔑 Authentification")

        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("email@example.com")
        self._email_input.setStyleSheet(self._input_style())

        self._password_input = QLineEdit()
        self._password_input.setPlaceholderText("Mot de passe")
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_input.setStyleSheet(self._input_style())

        self._btn_login = QPushButton("Se connecter")
        self._btn_login.setStyleSheet(self._btn_style("#f97316"))
        self._btn_login.clicked.connect(self._on_login)

        self._btn_logout = QPushButton("Déconnecter")
        self._btn_logout.setStyleSheet(self._btn_style("#dc2626"))
        self._btn_logout.clicked.connect(self._on_logout)

        self._auth_status = QLabel("")
        self._auth_status.setStyleSheet("font-size: 12px; color: #6b7280;")

        auth_form = QFormLayout()
        auth_form.setSpacing(10)
        auth_form.addRow("Email :", self._email_input)
        auth_form.addRow("Mot de passe :", self._password_input)

        auth_btn_row = QHBoxLayout()
        auth_btn_row.addWidget(self._btn_login)
        auth_btn_row.addWidget(self._btn_logout)
        auth_btn_row.addStretch()

        auth_box.layout().addLayout(auth_form)
        auth_box.layout().addLayout(auth_btn_row)
        auth_box.layout().addWidget(self._auth_status)
        main.addWidget(auth_box)

        # ── Groupe Mises à jour ───────────────────────────────────────────────
        update_box = self._make_group("🔄 Mises à jour")
        self._check_auto_update = QCheckBox("Vérifier les mises à jour au démarrage")
        self._check_auto_update.setChecked(True)
        self._btn_check_update = QPushButton("Vérifier maintenant")
        self._btn_check_update.setStyleSheet(self._btn_style("#8b5cf6"))
        self._btn_check_update.clicked.connect(self._on_check_update)
        self._update_status = QLabel("")
        self._update_status.setStyleSheet("font-size: 12px; color: #6b7280;")

        update_box.layout().addWidget(self._check_auto_update)
        update_box.layout().addWidget(self._btn_check_update)
        update_box.layout().addWidget(self._update_status)
        main.addWidget(update_box)

        main.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Pré-remplir depuis DB
        self._load_current_profile()
        self._update_auth_ui()
        get_state().auth_changed.connect(lambda *_: self._update_auth_ui())

    def _make_group(self, title: str) -> QGroupBox:
        box = QGroupBox(title)
        box.setStyleSheet("""
            QGroupBox { background: #ffffff; border-radius: 12px; border: 1px solid #e5e7eb;
                        font-size: 14px; font-weight: 700; color: #374151;
                        margin-top: 8px; padding: 16px; }
            QGroupBox::title { subcontrol-origin: margin; left: 14px; top: -8px;
                               background: #ffffff; padding: 0 4px; }
        """)
        box.setLayout(QVBoxLayout())
        box.layout().setSpacing(10)
        return box

    def _input_style(self) -> str:
        return """
            QLineEdit { background: #f8fafc; border: 1px solid #d1d5db; border-radius: 8px;
                        padding: 8px 12px; font-size: 13px; color: #1f2937; }
            QLineEdit:focus { border-color: #f97316; }
        """

    def _btn_style(self, color: str) -> str:
        return f"""
            QPushButton {{ background: {color}; color: white; border: none;
                           border-radius: 8px; padding: 8px 18px; font-weight: 600; font-size: 13px; }}
            QPushButton:hover {{ opacity: 0.9; }}
            QPushButton:disabled {{ background: #d1d5db; color: #9ca3af; }}
        """

    def _load_current_profile(self):
        from storage.repositories import get_active_profile
        profile = get_active_profile()
        if profile:
            self._url_input.setText(profile.get("url", ""))
            self._profile_name_input.setText(profile.get("name", ""))

    def _update_auth_ui(self):
        state = get_state()
        if state.is_authenticated:
            self._auth_status.setText(f"✅ Connecté en tant que {state.username}")
            self._auth_status.setStyleSheet("font-size: 12px; color: #16a34a; font-weight: 600;")
            self._btn_login.setEnabled(False)
            self._btn_logout.setEnabled(True)
        else:
            self._auth_status.setText("Non authentifié")
            self._auth_status.setStyleSheet("font-size: 12px; color: #dc2626;")
            self._btn_login.setEnabled(True)
            self._btn_logout.setEnabled(False)

    def _on_test_connection(self):
        url = self._url_input.text().strip()
        if not url:
            return
        self._conn_status.setText("Test en cours…")
        self._btn_test.setEnabled(False)

        class PingWorker(QThread):
            done = Signal(bool)
            def __init__(self, u): super().__init__(); self.u = u
            def run(self):
                from api.client import BRClient
                c = BRClient(self.u, timeout=5)
                self.done.emit(c.ping())
                c.close()

        self._ping_worker = PingWorker(url)
        self._ping_worker.done.connect(self._on_ping_done)
        self._ping_worker.start()

    @Slot(bool)
    def _on_ping_done(self, ok: bool):
        self._btn_test.setEnabled(True)
        if ok:
            self._conn_status.setText("✅ Serveur accessible")
            self._conn_status.setStyleSheet("font-size: 12px; color: #16a34a; font-weight: 600;")
        else:
            self._conn_status.setText("❌ Serveur inaccessible")
            self._conn_status.setStyleSheet("font-size: 12px; color: #dc2626; font-weight: 600;")

    def _on_save_server(self):
        url = self._url_input.text().strip()
        name = self._profile_name_input.text().strip() or "NAS local"
        if not url:
            return
        from storage.repositories import upsert_profile, set_active_profile
        from api.client import init_client
        pid = upsert_profile(name, url)
        set_active_profile(pid)
        init_client(url)
        get_state().set_connected(False, url)
        self._conn_status.setText("✅ Profil enregistré")
        self._conn_status.setStyleSheet("font-size: 12px; color: #16a34a;")
        log.info("Profile saved: %s → %s", name, url)

    def _on_login(self):
        email = self._email_input.text().strip()
        password = self._password_input.text()
        if not email or not password:
            self._auth_status.setText("⚠️ Email et mot de passe requis")
            return
        self._btn_login.setEnabled(False)
        self._btn_login.setText("Connexion…")
        self._auth_status.setText("Authentification en cours…")
        self._auth_status.setStyleSheet("font-size: 12px; color: #6b7280;")
        from storage.repositories import get_active_profile
        profile = get_active_profile()
        self._current_profile_name = profile["name"] if profile else "default"
        self._login_worker = LoginWorker(email, password, self._current_profile_name)
        self._login_worker.finished.connect(self._on_login_result)
        self._login_worker.start()

    @Slot(object)
    def _on_login_result(self, result):
        """Reçoit l'AuthResult de l'étape 1."""
        self._btn_login.setEnabled(True)
        self._btn_login.setText("Se connecter")

        if result.success:
            get_state().set_authenticated(True, result.username)
            return

        if result.needs_2fa:
            self._auth_status.setText("🔐 Code double authentification requis…")
            self._auth_status.setStyleSheet("font-size: 12px; color: #f97316; font-weight: 600;")
            self._ask_2fa_code(result.pending_token)
            return

        self._auth_status.setText(f"❌ {result.message}")
        self._auth_status.setStyleSheet("font-size: 12px; color: #dc2626; font-weight: 600;")

    def _ask_2fa_code(self, pending_token: str):
        """Affiche un dialog pour saisir le code TOTP, puis lance l'étape 2."""
        code, ok = QInputDialog.getText(
            self,
            "Double authentification",
            "Entrez le code à 6 chiffres de votre application d'authentification :",
            QLineEdit.EchoMode.Normal,
        )
        if not ok or not code.strip():
            self._auth_status.setText("⚠️ Connexion annulée — code 2FA non fourni")
            self._auth_status.setStyleSheet("font-size: 12px; color: #6b7280;")
            return

        self._btn_login.setEnabled(False)
        self._btn_login.setText("Vérification 2FA…")
        self._auth_status.setText("Vérification du code 2FA…")

        self._2fa_worker = TwoFAWorker(
            code.strip(), pending_token, self._current_profile_name
        )
        self._2fa_worker.finished.connect(self._on_2fa_result)
        self._2fa_worker.start()

    @Slot(object)
    def _on_2fa_result(self, result):
        """Reçoit l'AuthResult de l'étape 2 (TOTP)."""
        self._btn_login.setEnabled(True)
        self._btn_login.setText("Se connecter")

        if result.success:
            get_state().set_authenticated(True, result.username)
            return

        self._auth_status.setText(f"❌ {result.message}")
        self._auth_status.setStyleSheet("font-size: 12px; color: #dc2626; font-weight: 600;")

    def _on_logout(self):
        from api.auth_api import logout
        from storage.repositories import get_active_profile
        profile = get_active_profile()
        logout(profile["name"] if profile else "default")
        get_state().set_authenticated(False, "")

    def _on_check_update(self):
        self._btn_check_update.setEnabled(False)
        self._update_status.setText("Vérification…")

        class UpdateChecker(QThread):
            done = Signal(object)
            def run(self):
                from updater.updater import check_for_update
                self.done.emit(check_for_update())

        self._update_checker = UpdateChecker()
        self._update_checker.done.connect(self._on_update_check_done)
        self._update_checker.start()

    @Slot(object)
    def _on_update_check_done(self, release):
        self._btn_check_update.setEnabled(True)
        if release is None:
            self._update_status.setText("✅ Application à jour")
            self._update_status.setStyleSheet("font-size: 12px; color: #16a34a;")
            return

        self._update_status.setText(f"⬆️ Mise à jour v{release.version} disponible !")
        self._update_status.setStyleSheet("font-size: 12px; color: #f97316; font-weight: 700;")

        reply = QMessageBox.question(
            self,
            "Mise à jour disponible",
            f"La version {release.version} est disponible.\n\nTélécharger et installer maintenant ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._download_update(release)

    def _download_update(self, release):
        from PySide6.QtWidgets import QProgressDialog
        from PySide6.QtCore import QCoreApplication

        progress = QProgressDialog("Téléchargement de la mise à jour…", "Annuler", 0, 100, self)
        progress.setWindowTitle("Mise à jour")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.show()

        class DownloadWorker(QThread):
            progress_signal = Signal(int, int)
            done = Signal(object)
            def __init__(self, r): super().__init__(); self.r = r
            def run(self):
                from updater.updater import download_update
                def cb(d, t): self.progress_signal.emit(d, t or 1)
                path = download_update(self.r, progress_cb=cb)
                self.done.emit(path)

        self._dl_worker = DownloadWorker(release)
        self._dl_worker.progress_signal.connect(
            lambda d, t: progress.setValue(int(d / t * 100))
        )
        self._dl_worker.done.connect(lambda path: self._on_download_done(path, progress))
        self._dl_worker.start()

    def _on_download_done(self, zip_path, progress_dialog):
        progress_dialog.close()
        if zip_path is None:
            QMessageBox.critical(self, "Erreur", "Échec du téléchargement de la mise à jour.")
            return
        from updater.updater import apply_update
        apply_update(zip_path)   # quitte le process si OK
