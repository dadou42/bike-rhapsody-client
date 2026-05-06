"""
Modèle de configuration — chargé depuis SQLite via storage.repositories.
"""
from dataclasses import dataclass, field
from typing import Optional
from config.defaults import DEFAULT_SERVER_URL, DEFAULT_TIMEOUT, BUFFER_DIR, CACHE_DIR


@dataclass
class ServerProfile:
    name: str = "NAS local"
    url: str = DEFAULT_SERVER_URL
    profile_type: str = "local"   # local | remote | test
    is_active: bool = True
    last_connected: Optional[str] = None


@dataclass
class AppSettings:
    # Serveur actif
    active_profile: ServerProfile = field(default_factory=ServerProfile)
    server_timeout: int = DEFAULT_TIMEOUT

    # Chemins
    buffer_dir: str = str(BUFFER_DIR)
    cache_dir: str = str(CACHE_DIR)

    # Comportement upload
    auto_upload: bool = False
    validate_before_upload: bool = True
    keep_local_copy: bool = True
    generate_thumbnails: bool = True

    # UI
    theme: str = "dark"
    log_level: str = "INFO"

    # Sauvegarde
    backup_destination: str = ""
    backup_frequency: str = "weekly"   # daily | weekly | monthly
    backup_retention_daily: int = 7
    backup_retention_weekly: int = 4
    backup_retention_monthly: int = 12

    # Mise à jour
    auto_check_updates: bool = True
