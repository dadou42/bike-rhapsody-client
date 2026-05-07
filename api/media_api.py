"""
API Bike Rhapsody — endpoints médias.
"""
from pathlib import Path
from typing import Optional
from api.client import get_client
from logs.logger import get_logger

log = get_logger("api.media")

CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB


def upload_media(
    local_path: str,
    sha256: Optional[str] = None,
    activity_id: Optional[str] = None,
    captured_at: Optional[str] = None,
    gps_lat: Optional[float] = None,
    gps_lon: Optional[float] = None,
    progress_cb=None,
) -> dict:
    """
    Upload un fichier média vers Bike Rhapsody (endpoint orphan).
    Retourne la réponse JSON {ok, id, duplicate, size, sha256}.
    Lève une exception en cas d'erreur.
    """
    client = get_client()
    path = Path(local_path)
    size = path.stat().st_size
    log.info("Uploading %s (%s)", path.name, _fmt_size(size))

    fields: dict = {}
    if sha256:
        fields["sha256"] = sha256
    if activity_id:
        fields["activity_id"] = str(activity_id)
    if captured_at:
        fields["captured_at"] = captured_at
    if gps_lat is not None:
        fields["gps_lat"] = str(gps_lat)
    if gps_lon is not None:
        fields["gps_lon"] = str(gps_lon)

    # Multipart upload — timeout étendu pour gros fichiers
    with open(path, "rb") as f:
        files = {"file": (path.name, f, _mime_type(path))}
        # Note : la progression réelle d'upload nécessite un client httpx
        # avec hook personnalisé ; pour l'instant on émet 50% au start et
        # 100% à la fin pour donner un retour visuel.
        if progress_cb:
            progress_cb(0, size)
        r = client.post(
            "/api/media/upload",
            files=files,
            data=fields,
            timeout=300,  # 5 minutes pour les gros fichiers
        )
        if progress_cb:
            progress_cb(size, size)

    if r.status_code not in (200, 201):
        detail = _extract_error(r)
        raise RuntimeError(f"Upload failed HTTP {r.status_code}: {detail}")

    data = r.json()
    log.info("Upload OK: %s → server id=%s%s",
             path.name, data.get("id"),
             " (duplicate)" if data.get("duplicate") else "")
    return data


def check_checksum_server(sha256_hex: str) -> bool:
    """Vérifie si un média avec ce sha256 existe déjà sur le serveur."""
    try:
        r = get_client().get(f"/api/media/checksum/{sha256_hex}")
        if r.status_code == 200:
            return r.json().get("exists", False)
    except Exception as e:
        log.debug("Checksum check failed: %s", e)
    return False


def link_to_activity(server_media_id: str, activity_id: str) -> bool:
    """Rattache un média à une activité."""
    try:
        r = get_client().post(
            "/api/media/link-activity",
            json={"media_id": server_media_id, "activity_id": activity_id},
        )
        return r.status_code == 200
    except Exception as e:
        log.error("Link to activity failed: %s", e)
        return False


def get_recent_activities(limit: int = 30) -> list[dict]:
    """Récupère les activités récentes pour le matching."""
    try:
        r = get_client().get(f"/api/activities/recent?limit={limit}")
        if r.status_code == 200:
            data = r.json()
            # BR retourne soit une liste, soit {"items": [...]}
            if isinstance(data, list):
                return data
            return data.get("items", data.get("activities", []))
    except Exception as e:
        log.warning("get_recent_activities failed: %s", e)
    return []


def _mime_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".heic": "image/heic",
        ".webp": "image/webp", ".gif": "image/gif",
        ".mp4": "video/mp4", ".mov": "video/quicktime",
        ".m4v": "video/x-m4v",
    }.get(ext, "application/octet-stream")


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    if n < 1024 ** 2:
        return f"{n/1024:.1f}KB"
    if n < 1024 ** 3:
        return f"{n/1024**2:.1f}MB"
    return f"{n/1024**3:.2f}GB"


def _extract_error(r) -> str:
    try:
        return r.json().get("detail") or r.json().get("error") or r.text[:200]
    except Exception:
        return r.text[:200]
