"""
Modèle de données média — statuts, types, formats acceptés.
"""
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class MediaStatus(str, Enum):
    DISCOVERED         = "discovered"
    SCANNING           = "scanning"
    DUPLICATE          = "duplicate"
    WAITING_METADATA   = "waiting_metadata"
    WAITING_LINK       = "waiting_activity_link"
    READY              = "ready_to_upload"
    UPLOADING          = "uploading"
    UPLOADED           = "uploaded"
    FAILED             = "failed"
    IGNORED            = "ignored"
    ARCHIVED           = "archived"


class MediaType(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    FIT   = "fit"
    GPX   = "gpx"
    OTHER = "other"


PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tiff", ".tif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".insv"}
FIT_EXTENSIONS   = {".fit"}
GPX_EXTENSIONS   = {".gpx"}

ALL_MEDIA_EXTENSIONS = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS | FIT_EXTENSIONS | GPX_EXTENSIONS


def get_media_type(path: str) -> MediaType:
    ext = path.lower().rsplit(".", 1)[-1]
    ext = f".{ext}"
    if ext in PHOTO_EXTENSIONS:
        return MediaType.PHOTO
    if ext in VIDEO_EXTENSIONS:
        return MediaType.VIDEO
    if ext in FIT_EXTENSIONS:
        return MediaType.FIT
    if ext in GPX_EXTENSIONS:
        return MediaType.GPX
    return MediaType.OTHER


@dataclass
class MediaFile:
    local_path: str
    original_name: str = ""
    file_type: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    sha256: str = ""
    status: str = MediaStatus.DISCOVERED
    activity_id: Optional[str] = None
    activity_match_score: Optional[float] = None
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    gps_alt: Optional[float] = None
    captured_at: Optional[str] = None
    tags: str = ""
    notes: str = ""
    server_media_id: Optional[str] = None
    thumbnail_path: Optional[str] = None
    # Métadonnées enrichies (non persistées directement)
    width: Optional[int] = None
    height: Optional[int] = None
    duration_s: Optional[float] = None
    camera_make: Optional[str] = None
    camera_model: Optional[str] = None
    db_id: Optional[int] = None
