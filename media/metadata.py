"""
Lecture des métadonnées médias : EXIF photos, info vidéos.
"""
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from media.media_model import MediaFile, MediaType, get_media_type
from logs.logger import get_logger

log = get_logger("media.metadata")


def _parse_exif_datetime(s: str) -> Optional[str]:
    """Convertit 'YYYY:MM:DD HH:MM:SS' → ISO 8601."""
    if not s:
        return None
    try:
        dt = datetime.strptime(s.strip(), "%Y:%m:%d %H:%M:%S")
        return dt.isoformat()
    except ValueError:
        return None


def _read_photo_metadata(path: Path, media: MediaFile) -> None:
    """Lit les métadonnées EXIF d'une photo via Pillow."""
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS

        with Image.open(path) as img:
            media.width, media.height = img.size
            media.mime_type = Image.MIME.get(img.format or "", "image/jpeg")

            exif_raw = img._getexif()  # type: ignore[attr-defined]
            if not exif_raw:
                return

            exif = {TAGS.get(k, k): v for k, v in exif_raw.items()}

            # Date de prise
            for key in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
                if key in exif:
                    media.captured_at = _parse_exif_datetime(str(exif[key]))
                    if media.captured_at:
                        break

            # Appareil
            media.camera_make = str(exif.get("Make", "")).strip() or None
            media.camera_model = str(exif.get("Model", "")).strip() or None

            # GPS
            gps_info = exif.get("GPSInfo")
            if gps_info:
                gps = {GPSTAGS.get(k, k): v for k, v in gps_info.items()}
                lat = _dms_to_decimal(
                    gps.get("GPSLatitude"), gps.get("GPSLatitudeRef", "N")
                )
                lon = _dms_to_decimal(
                    gps.get("GPSLongitude"), gps.get("GPSLongitudeRef", "E")
                )
                alt_raw = gps.get("GPSAltitude")
                if lat is not None:
                    media.gps_lat = lat
                if lon is not None:
                    media.gps_lon = lon
                if alt_raw is not None:
                    try:
                        media.gps_alt = float(alt_raw)
                    except Exception:
                        pass

    except Exception as e:
        log.debug("EXIF read failed for %s: %s", path.name, e)


def _dms_to_decimal(dms, ref: str) -> Optional[float]:
    """Convertit degrés/minutes/secondes en décimal."""
    if not dms or len(dms) < 3:
        return None
    try:
        d = float(dms[0])
        m = float(dms[1])
        s = float(dms[2])
        val = d + m / 60 + s / 3600
        if ref in ("S", "W"):
            val = -val
        return round(val, 7)
    except Exception:
        return None


def _read_video_metadata(path: Path, media: MediaFile) -> None:
    """Lit les métadonnées vidéo via ffprobe (si disponible)."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                str(path),
            ],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return

        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        tags = fmt.get("tags", {})

        # Durée
        duration = fmt.get("duration")
        if duration:
            media.duration_s = float(duration)

        # Date
        for key in ("creation_time", "com.apple.quicktime.creationdate"):
            val = tags.get(key)
            if val:
                try:
                    dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                    media.captured_at = dt.isoformat()
                    break
                except Exception:
                    pass

        # Résolution
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                media.width = stream.get("width")
                media.height = stream.get("height")
                break

        media.mime_type = "video/mp4"

    except (FileNotFoundError, subprocess.TimeoutExpired):
        log.debug("ffprobe not available for %s", path.name)
    except Exception as e:
        log.debug("Video metadata failed for %s: %s", path.name, e)


def enrich_metadata(media: MediaFile) -> MediaFile:
    """
    Enrichit un MediaFile avec ses métadonnées.
    Modifie l'objet en place et le retourne.
    """
    path = Path(media.local_path)
    media_type = get_media_type(media.local_path)

    media.file_type = media_type.value
    media.original_name = path.name

    if not media.size_bytes:
        try:
            media.size_bytes = path.stat().st_size
        except Exception:
            pass

    if media_type == MediaType.PHOTO:
        _read_photo_metadata(path, media)
    elif media_type == MediaType.VIDEO:
        _read_video_metadata(path, media)

    # Fallback date : date de modification du fichier
    if not media.captured_at:
        try:
            mtime = path.stat().st_mtime
            media.captured_at = datetime.fromtimestamp(mtime).isoformat()
        except Exception:
            pass

    return media
