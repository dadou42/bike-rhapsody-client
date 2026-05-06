"""
Initialisation au démarrage : DB, logging, client HTTP, session.
"""
from logs.logger import setup_logging, get_logger
from storage.local_db import init_db
from storage.repositories import get_setting, set_setting, get_active_profile, upsert_profile, set_active_profile
from api.client import init_client
from api.auth_api import restore_session
from app.app_state import get_state
from config.defaults import DEFAULT_SERVER_URL, DEFAULT_TIMEOUT
from config.settings import AppSettings

log = get_logger("bootstrap")


def bootstrap() -> AppSettings:
    """Lance tout ce qui est nécessaire avant d'afficher la fenêtre principale."""

    # 1. Logging
    setup_logging(get_setting("log_level") or "INFO")
    log.info("=== Bike Rhapsody Mac Client starting ===")

    # 2. SQLite
    init_db()

    # 3. Profil serveur actif
    profile = get_active_profile()
    if not profile:
        # Premier lancement : créer le profil par défaut
        pid = upsert_profile("NAS local", DEFAULT_SERVER_URL, "local")
        set_active_profile(pid)
        profile = get_active_profile()

    server_url = profile["url"] if profile else DEFAULT_SERVER_URL
    profile_name = profile["name"] if profile else "default"

    # 4. Client HTTP
    init_client(server_url, DEFAULT_TIMEOUT)

    # 5. Test de connectivité
    state = get_state()
    from api.client import get_client
    client = get_client()

    if client.ping():
        state.set_connected(True, server_url)
        log.info("Server reachable at %s", server_url)

        version = client.get_server_version()
        if version:
            state.set_server_version(version)

        # Restaurer la session
        if restore_session(profile_name):
            from api.auth_api import get_current_user
            user = get_current_user()
            username = user.get("email", "") if user else ""
            state.set_authenticated(True, username)
            log.info("Session restored for '%s'", username)
        else:
            log.info("No saved session — login required")
    else:
        state.set_connected(False, server_url)
        log.warning("Server not reachable at %s", server_url)

    # 6. Reconstruire AppSettings depuis DB
    settings = AppSettings()
    settings.active_profile.url = server_url
    settings.active_profile.name = profile_name
    log.info("Bootstrap complete")
    return settings
