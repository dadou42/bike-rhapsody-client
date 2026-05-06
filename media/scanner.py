"""
Scanner de dossier — découverte récursive des médias acceptés.
Utilisé pour l'import manuel et les dossiers surveillés.
"""
import os
from pathlib import Path
from typing import Generator, Callable, Optional

from media.media_model import MediaFile, MediaStatus, ALL_MEDIA_EXTENSIONS, get_media_type
from media.checksum import sha256 as compute_sha256
from media.metadata import enrich_metadata
from media.deduplicate import check_duplicate
from media.thumbnails import generate_thumbnail
from storage.local_db import db
from logs.logger import get_logger

log = get_logger("media.scanner")


def discover_files(root: str | Path) -> Generator[Path, None, None]:
    """Yield récursif de tous les fichiers médias dans root."""
    root = Path(root)
    if root.is_file():
        if root.suffix.lower() in ALL_MEDIA_EXTENSIONS:
            yield root
        return

    for dirpath, dirnames, filenames in os.walk(root):
        # Ignorer les dossiers cachés et MACOSX
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d != "__MACOSX"
        ]
        for fname in filenames:
            if fname.startswith("."):
                continue
            p = Path(dirpath) / fname
            if p.suffix.lower() in ALL_MEDIA_EXTENSIONS:
                yield p


def _save_media_to_db(media: MediaFile) -> int:
    cur = db().execute(
        """INSERT INTO media_files
           (local_path, original_name, file_type, mime_type, size_bytes, sha256,
            status, gps_lat, gps_lon, gps_alt, captured_at, tags, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            media.local_path, media.original_name, media.file_type, media.mime_type,
            media.size_bytes, media.sha256, media.status,
            media.gps_lat, media.gps_lon, media.gps_alt,
            media.captured_at, media.tags, media.notes,
        ),
    )
    db().commit()
    return cur.lastrowid


def _add_to_queue(media_db_id: int) -> None:
    db().execute(
        "INSERT INTO upload_queue (media_id, status) VALUES (?, 'pending')",
        (media_db_id,),
    )
    db().commit()


def scan_and_process(
    root: str | Path,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    auto_queue: bool = False,
) -> list[MediaFile]:
    """
    Scanne root, enrichit les métadonnées, calcule les checksums,
    détecte les doublons, génère les miniatures, persiste en DB.

    progress_cb(current, total, filename) — appelé pour chaque fichier.
    auto_queue=True → ajoute automatiquement à la file d'upload.

    Retourne la liste des MediaFile traités.
    """
    paths = list(discover_files(root))
    total = len(paths)
    log.info("Scan started: %d files in %s", total, root)

    results: list[MediaFile] = []

    for i, path in enumerate(paths):
        fname = path.name
        if progress_cb:
            progress_cb(i, total, fname)

        media = MediaFile(
            local_path=str(path),
            original_name=fname,
            status=MediaStatus.SCANNING,
        )

        try:
            # 1. Métadonnées
            enrich_metadata(media)

            # 2. Checksum
            media.sha256 = compute_sha256(path)

            # 3. Déduplication
            dup = check_duplicate(str(path), media.sha256)
            if dup["is_duplicate"]:
                media.status = MediaStatus.DUPLICATE
                log.debug("Duplicate: %s (source=%s)", fname, dup["source"])
            else:
                media.status = MediaStatus.READY

            # 4. Persister en DB (sauf si doublon local exact)
            if not (dup["is_duplicate"] and dup["source"] == "local"):
                media.db_id = _save_media_to_db(media)

                # 5. Miniature
                if media.db_id and media.status == MediaStatus.READY:
                    thumb = generate_thumbnail(str(path), media.sha256)
                    media.thumbnail_path = thumb

                # 6. File d'attente auto
                if auto_queue and media.status == MediaStatus.READY and media.db_id:
                    _add_to_queue(media.db_id)

        except Exception as e:
            log.error("Scan error for %s: %s", fname, e)
            media.status = MediaStatus.FAILED

        results.append(media)

    if progress_cb:
        progress_cb(total, total, "Terminé")

    log.info(
        "Scan done: %d total, %d ready, %d duplicates, %d errors",
        total,
        sum(1 for m in results if m.status == MediaStatus.READY),
        sum(1 for m in results if m.status == MediaStatus.DUPLICATE),
        sum(1 for m in results if m.status == MediaStatus.FAILED),
    )
    return results
