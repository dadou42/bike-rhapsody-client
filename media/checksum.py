"""
Calcul SHA256 d'un fichier — lecture par blocs pour les gros fichiers.
"""
import hashlib
from pathlib import Path
from logs.logger import get_logger

log = get_logger("media.checksum")

BLOCK_SIZE = 65536  # 64 KB


def sha256(path: str | Path, progress_cb=None) -> str:
    """
    Calcule le SHA256 du fichier.
    progress_cb(bytes_read, total_bytes) — optionnel.
    """
    p = Path(path)
    total = p.stat().st_size
    h = hashlib.sha256()
    read = 0

    with open(p, "rb") as f:
        while chunk := f.read(BLOCK_SIZE):
            h.update(chunk)
            read += len(chunk)
            if progress_cb:
                progress_cb(read, total)

    digest = h.hexdigest()
    log.debug("SHA256 %s → %s…", p.name, digest[:12])
    return digest


def quick_hash(path: str | Path, sample_bytes: int = 131072) -> str:
    """
    Hash rapide : début + milieu + fin du fichier (pour pré-déduplication).
    Ne remplace pas sha256 mais évite de tout lire pour les gros fichiers.
    """
    p = Path(path)
    size = p.stat().st_size
    h = hashlib.md5()
    h.update(str(size).encode())

    with open(p, "rb") as f:
        # Début
        h.update(f.read(sample_bytes))
        # Milieu
        mid = max(0, size // 2 - sample_bytes // 2)
        f.seek(mid)
        h.update(f.read(sample_bytes))
        # Fin
        end = max(0, size - sample_bytes)
        f.seek(end)
        h.update(f.read(sample_bytes))

    return h.hexdigest()
