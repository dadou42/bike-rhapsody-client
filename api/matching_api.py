"""
API client pour la phase 3 — matching orphan_media ↔ activités.
"""
from typing import Optional

from api.client import get_client
from logs.logger import get_logger

log = get_logger("api.matching")


def list_activities(limit: int = 50) -> list[dict]:
    """Liste les activités du user avec compteur de médias liés."""
    try:
        r = get_client().get(f"/api/media/activities", params={"limit": limit})
        if r.status_code == 200:
            return r.json().get("items", []) or []
        log.warning("list_activities HTTP %s", r.status_code)
    except Exception as e:
        log.error("list_activities failed: %s", e)
    return []


def list_orphans(only_unmatched: bool = True, limit: int = 200) -> list[dict]:
    """Liste les médias orphelins de l'user (par défaut non liés)."""
    try:
        r = get_client().get(
            "/api/media/orphans",
            params={"only_unmatched": str(only_unmatched).lower(), "limit": limit},
        )
        if r.status_code == 200:
            return r.json().get("items", []) or []
        log.warning("list_orphans HTTP %s", r.status_code)
    except Exception as e:
        log.error("list_orphans failed: %s", e)
    return []


def match_orphans(tolerance_minutes: int = 30, dry_run: bool = False) -> dict:
    """
    Lance le matching automatique. Retourne :
    {matched, candidates, activities_scanned, tolerance_minutes, dry_run, details[]}
    """
    try:
        r = get_client().post(
            "/api/media/match-orphans",
            params={"tolerance_minutes": tolerance_minutes,
                    "dry_run": str(dry_run).lower()},
            timeout=60,
        )
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}", "matched": 0}
    except Exception as e:
        log.error("match_orphans failed: %s", e)
        return {"error": str(e), "matched": 0}


def link_orphan(media_id: int, activity_id: int) -> bool:
    try:
        r = get_client().post(
            f"/api/media/orphans/{media_id}/link",
            params={"activity_id": activity_id},
        )
        return r.status_code == 200
    except Exception as e:
        log.error("link_orphan failed: %s", e)
        return False


def sync_metadata(updates: list[dict]) -> dict:
    """
    Pousse en batch les métadonnées (captured_at, gps) au serveur.
    `updates` = [{"sha256": str, "captured_at": str, "gps_lat": float|None,
                  "gps_lon": float|None, "gps_alt": float|None}, ...]
    Le serveur ne touche que les champs NULL côté serveur (pas d'écrasement).
    Retourne {ok, received, updated, not_found, no_change_needed}.
    """
    if not updates:
        return {"ok": True, "received": 0, "updated": 0, "not_found": 0}
    try:
        r = get_client().post(
            "/api/media/sync-metadata",
            json={"updates": updates},
            timeout=60,
        )
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}", "updated": 0}
    except Exception as e:
        log.error("sync_metadata failed: %s", e)
        return {"error": str(e), "updated": 0}


def unlink_orphan(media_id: int) -> bool:
    try:
        r = get_client().delete(f"/api/media/orphans/{media_id}/link")
        return r.status_code == 200
    except Exception as e:
        log.error("unlink_orphan failed: %s", e)
        return False
