"""
Génération de miniatures — photos et vidéos.
Cache dans ~/Library/Caches/BikeRhapsodyClient/thumbnails/
"""
import subprocess
from pathlib import Path
from typing import Optional

from config.defaults import CACHE_DIR
from media.media_model import MediaType, get_media_type
from logs.logger import get_logger

log = get_logger("media.thumbnails")

THUMB_DIR = CACHE_DIR / "thumbnails"
THUMB_SIZE_SMALL  = (120, 90)
THUMB_SIZE_MEDIUM = (320, 240)


def _ensure_thumb_dir() -> None:
    THUMB_DIR.mkdir(parents=True, exist_ok=True)


def get_thumbnail_path(sha256: str, size: str = "medium") -> Path:
    return THUMB_DIR / f"{sha256[:2]}" / f"{sha256}_{size}.jpg"


def generate_thumbnail(
    local_path: str,
    sha256: str,
    size: str = "medium",
    force: bool = False,
) -> Optional[str]:
    """
    Génère une miniature et retourne son chemin local.
    Retourne None en cas d'échec.
    size : 'small' (120×90) | 'medium' (320×240)
    """
    _ensure_thumb_dir()
    thumb_path = get_thumbnail_path(sha256, size)

    if thumb_path.exists() and not force:
        return str(thumb_path)

    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    media_type = get_media_type(local_path)

    if media_type == MediaType.PHOTO:
        return _thumb_photo(local_path, thumb_path, size)
    elif media_type == MediaType.VIDEO:
        return _thumb_video(local_path, thumb_path, size)

    return None


def _thumb_photo(src: str, dst: Path, size: str) -> Optional[str]:
    try:
        from PIL import Image, ImageOps

        dims = THUMB_SIZE_MEDIUM if size == "medium" else THUMB_SIZE_SMALL
        with Image.open(src) as img:
            # Corriger l'orientation EXIF
            img = ImageOps.exif_transpose(img)
            img.thumbnail(dims, Image.Resampling.LANCZOS)
            img = img.convert("RGB")
            img.save(str(dst), "JPEG", quality=82, optimize=True)
        log.debug("Thumb OK: %s", dst.name)
        return str(dst)
    except Exception as e:
        log.debug("Thumb photo failed for %s: %s", Path(src).name, e)
        return None


def _thumb_video(src: str, dst: Path, size: str) -> Optional[str]:
    """Extrait une frame à 10% de la durée via ffmpeg."""
    dims = THUMB_SIZE_MEDIUM if size == "medium" else THUMB_SIZE_SMALL
    scale = f"{dims[0]}:{dims[1]}"
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", "0",
                "-i", src,
                "-vf", f"select=gt(scene\\,0.1),scale={scale}:force_original_aspect_ratio=decrease",
                "-vframes", "1",
                "-q:v", "3",
                str(dst),
            ],
            capture_output=True, timeout=20
        )
        if dst.exists():
            log.debug("Video thumb OK: %s", dst.name)
            return str(dst)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # ffmpeg pas dispo — essai basique sans filtre scène
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", "3", "-i", src,
                 "-vf", f"scale={scale}:force_original_aspect_ratio=decrease",
                 "-vframes", "1", "-q:v", "3", str(dst)],
                capture_output=True, timeout=20, check=True
            )
            if dst.exists():
                return str(dst)
        except Exception:
            pass
    except Exception as e:
        log.debug("Video thumb failed for %s: %s", Path(src).name, e)
    return None


def clear_cache() -> int:
    """Supprime tout le cache de miniatures. Retourne le nombre de fichiers supprimés."""
    import shutil
    count = sum(1 for _ in THUMB_DIR.rglob("*.jpg"))
    shutil.rmtree(THUMB_DIR, ignore_errors=True)
    log.info("Thumbnail cache cleared: %d files", count)
    return count
