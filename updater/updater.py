"""
Auto-update via GitHub Releases.

Mécanisme :
  1. Vérifie la dernière release sur GitHub API
  2. Compare avec la version embarquée (version.json)
  3. Si plus récente : télécharge l'asset .app.zip dans /tmp
  4. Lance un script bash qui remplace le .app en cours et relance l'app
  5. Quitte le process courant

Le script bash attend 1,5s (le temps que Python quitte) avant de remplacer.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from config.defaults import GITHUB_RELEASES_URL, ASSET_NAME
from logs.logger import get_logger

log = get_logger("updater")


def _load_current_version() -> str:
    """Charge la version depuis version.json embarqué dans le bundle ou le répertoire courant."""
    candidates = [
        Path(sys.executable).parent / "version.json",          # dans le .app PyInstaller
        Path(__file__).parent.parent / "version.json",         # en développement
    ]
    for p in candidates:
        if p.exists():
            try:
                return json.loads(p.read_text())["version"]
            except Exception:
                pass
    return "0.0.0"


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v))


@dataclass
class ReleaseInfo:
    version: str
    download_url: str
    release_notes: str
    published_at: str


def check_for_update(timeout: int = 10) -> Optional[ReleaseInfo]:
    """
    Interroge GitHub Releases API.
    Retourne un ReleaseInfo si une mise à jour est disponible, sinon None.
    """
    current = _load_current_version()
    log.info("Checking for update (current: %s) …", current)

    try:
        r = httpx.get(
            GITHUB_RELEASES_URL,
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json"},
            follow_redirects=True,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        log.warning("Update check failed: %s", e)
        return None

    latest_tag = data.get("tag_name", "").lstrip("v")
    if not latest_tag:
        return None

    if _version_tuple(latest_tag) <= _version_tuple(current):
        log.info("Already up to date (%s)", current)
        return None

    # Chercher l'asset universel
    asset_url = None
    for asset in data.get("assets", []):
        if asset["name"] == ASSET_NAME:
            asset_url = asset["browser_download_url"]
            break

    if not asset_url:
        log.warning("Update v%s found but asset '%s' not in release", latest_tag, ASSET_NAME)
        return None

    log.info("Update available: %s → %s", current, latest_tag)
    return ReleaseInfo(
        version=latest_tag,
        download_url=asset_url,
        release_notes=data.get("body", ""),
        published_at=data.get("published_at", ""),
    )


def download_update(release: ReleaseInfo, progress_cb=None) -> Optional[Path]:
    """
    Télécharge l'archive .app.zip dans un répertoire temporaire.
    progress_cb(downloaded_bytes, total_bytes) — optionnel.
    Retourne le chemin du zip téléchargé.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="br_update_"))
    zip_path = tmp_dir / ASSET_NAME
    log.info("Downloading update to %s …", zip_path)

    try:
        with httpx.stream("GET", release.download_url, follow_redirects=True, timeout=120) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(zip_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)
    except Exception as e:
        log.error("Download failed: %s", e)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return None

    log.info("Download complete: %.1f MB", zip_path.stat().st_size / 1_000_000)
    return zip_path


def _get_current_app_path() -> Optional[Path]:
    """Trouve le chemin du .app bundle en cours d'exécution."""
    exe = Path(sys.executable)
    # PyInstaller : .../BikeRhapsodyClient.app/Contents/MacOS/BikeRhapsodyClient
    for parent in exe.parents:
        if parent.suffix == ".app":
            return parent
    # Mode développement : pas de .app
    return None


def apply_update(zip_path: Path) -> bool:
    """
    Extrait le nouveau .app depuis zip_path puis lance le script de remplacement.
    Le process courant se termine après l'appel à cette fonction.
    """
    current_app = _get_current_app_path()
    if not current_app:
        log.error("Cannot apply update: not running from a .app bundle")
        return False

    tmp_dir = zip_path.parent
    log.info("Extracting update archive …")

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_dir)
    except Exception as e:
        log.error("Extraction failed: %s", e)
        return False

    # Trouver le .app extrait
    new_app = next(tmp_dir.glob("*.app"), None)
    if not new_app:
        log.error("No .app found in extracted archive")
        return False

    # Script bash : attendre que Python quitte, remplacer, relancer
    script = f"""#!/bin/bash
sleep 1.5
rm -rf "{current_app}"
cp -r "{new_app}" "{current_app}"
open "{current_app}"
rm -rf "{tmp_dir}"
"""
    script_path = Path(tempfile.mktemp(suffix=".sh"))
    script_path.write_text(script)
    script_path.chmod(0o755)

    log.info("Launching update helper script, then exiting …")
    subprocess.Popen(["bash", str(script_path)], close_fds=True)
    sys.exit(0)
