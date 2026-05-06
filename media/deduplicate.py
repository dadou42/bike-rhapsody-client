"""
Déduplication locale et serveur.

Niveaux de vérification (du plus rapide au plus fiable) :
  1. Quick hash (md5 début+milieu+fin) → pré-filtre rapide
  2. SHA256 exact → confirmation locale
  3. Vérification serveur via /api/media/checksum/{sha256}
"""
from pathlib import Path
from typing import Optional

from media.checksum import sha256 as compute_sha256, quick_hash
from storage.local_db import db
from logs.logger import get_logger

log = get_logger("media.deduplicate")


def is_duplicate_local(path: str, computed_sha256: Optional[str] = None) -> Optional[dict]:
    """
    Vérifie si le fichier existe déjà en base locale.
    Retourne le dict du media existant, ou None.
    """
    if not computed_sha256:
        return None

    row = db().execute(
        "SELECT * FROM media_files WHERE sha256 = ? AND status != 'ignored' LIMIT 1",
        (computed_sha256,),
    ).fetchone()

    if row:
        log.debug("Duplicate found locally: %s → id=%s", Path(path).name, row["id"])
        return dict(row)
    return None


def is_duplicate_server(sha256_hex: str) -> bool:
    """
    Vérifie si le fichier existe déjà sur le serveur Bike Rhapsody.
    Retourne True si doublon serveur.
    """
    try:
        from api.client import get_client
        client = get_client()
        r = client.get(f"/api/media/checksum/{sha256_hex}")
        if r.status_code == 200:
            data = r.json()
            exists = data.get("exists", False)
            if exists:
                log.debug("Duplicate on server: %s…", sha256_hex[:12])
            return exists
        return False
    except Exception as e:
        log.debug("Server dedup check failed: %s", e)
        return False


def check_duplicate(path: str, computed_sha256: Optional[str] = None) -> dict:
    """
    Vérification complète de doublon.

    Retourne :
    {
        "is_duplicate": bool,
        "source": "local" | "server" | None,
        "existing": dict | None,   # données du media existant si local
    }
    """
    result = {"is_duplicate": False, "source": None, "existing": None}

    # Local d'abord
    local = is_duplicate_local(path, computed_sha256)
    if local:
        result.update({"is_duplicate": True, "source": "local", "existing": local})
        return result

    # Serveur ensuite (seulement si authentifié)
    if computed_sha256:
        try:
            from app.app_state import get_state
            if get_state().is_authenticated:
                if is_duplicate_server(computed_sha256):
                    result.update({"is_duplicate": True, "source": "server"})
        except Exception:
            pass

    return result
