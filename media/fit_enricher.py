"""
Enrichissement GPS des photos depuis un fichier FIT.

Usage typique :
  1. enricher = FitEnricher.from_files(["track.fit"])
  2. for photo in photos: enricher.enrich(photo)  # backfill gps_lat/lon si match
  3. enricher.write_back_exif(photo)  # optionnel : écrire GPS dans le JPG

Stratégie de matching :
  - Timestamps en UTC dans le FIT
  - captured_at de la photo (EXIF DateTime → généralement local)
  - Tolérance configurable (±5min par défaut) — au-delà, pas d'enrichissement
  - Interpolation linéaire entre les 2 points FIT encadrant le timestamp
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Iterable

from logs.logger import get_logger

log = get_logger("media.fit_enricher")


@dataclass
class GpsPoint:
    timestamp: datetime  # UTC
    lat: float
    lon: float
    alt: Optional[float] = None


@dataclass
class FitTrack:
    """Une trace GPS complète issue d'un fichier FIT."""
    source_path: str
    points: list[GpsPoint]

    @property
    def start(self) -> Optional[datetime]:
        return self.points[0].timestamp if self.points else None

    @property
    def end(self) -> Optional[datetime]:
        return self.points[-1].timestamp if self.points else None

    def __len__(self) -> int:
        return len(self.points)


def parse_fit(fit_path: str) -> Optional[FitTrack]:
    """Parse un .fit et retourne la liste de points GPS triés par timestamp."""
    try:
        from fitparse import FitFile
    except ImportError:
        log.error("fitparse non installé — pip install fitparse")
        return None

    try:
        ff = FitFile(fit_path)
        points: list[GpsPoint] = []
        for record in ff.get_messages("record"):
            data = {f.name: f.value for f in record.fields}
            ts = data.get("timestamp")
            lat_semi = data.get("position_lat")
            lon_semi = data.get("position_long")
            alt = data.get("altitude") or data.get("enhanced_altitude")
            if ts is None or lat_semi is None or lon_semi is None:
                continue
            # FIT stocke en semicercles (1 deg = 2^31/180 semicercles)
            lat = lat_semi * (180.0 / 2 ** 31)
            lon = lon_semi * (180.0 / 2 ** 31)
            # Normaliser timestamp en UTC
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
            points.append(GpsPoint(ts, lat, lon, alt))
        points.sort(key=lambda p: p.timestamp)
        log.info("FIT parsed: %s → %d points GPS (%s → %s)",
                 Path(fit_path).name, len(points),
                 points[0].timestamp.isoformat() if points else "—",
                 points[-1].timestamp.isoformat() if points else "—")
        return FitTrack(source_path=fit_path, points=points)
    except Exception as e:
        log.error("FIT parse error pour %s : %s", fit_path, e)
        return None


def _parse_captured_at(s: str) -> Optional[datetime]:
    """Parse un captured_at (formats EXIF/ISO variés)."""
    if not s:
        return None
    # Formats possibles
    formats = [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                # captured_at EXIF est en LOCAL — on assume tz système
                dt = dt.astimezone()
            return dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


class FitEnricher:
    """Agrège un ou plusieurs FIT et enrichit les photos par interpolation."""

    def __init__(self, tracks: list[FitTrack], tolerance_seconds: int = 300):
        self.tracks = tracks
        self.tolerance = timedelta(seconds=tolerance_seconds)

    @classmethod
    def from_files(cls, fit_paths: Iterable[str], tolerance_seconds: int = 300) -> "FitEnricher":
        tracks = []
        for p in fit_paths:
            t = parse_fit(p)
            if t and t.points:
                tracks.append(t)
        return cls(tracks, tolerance_seconds)

    def is_empty(self) -> bool:
        return not self.tracks or all(not t.points for t in self.tracks)

    def find_gps(self, captured_at: str) -> Optional[tuple[float, float, Optional[float]]]:
        """Cherche le GPS pour un timestamp donné. Retourne (lat, lon, alt) ou None."""
        if self.is_empty():
            return None
        target = _parse_captured_at(captured_at)
        if target is None:
            log.debug("captured_at non parsable : %s", captured_at)
            return None

        # Pour chaque track, vérifier si le target tombe dans la fenêtre
        for track in self.tracks:
            if not track.points:
                continue
            start, end = track.points[0].timestamp, track.points[-1].timestamp
            # Tolérance : target doit être dans [start - tol, end + tol]
            if target < start - self.tolerance or target > end + self.tolerance:
                continue

            # Recherche dichotomique du point le plus proche
            best = None
            best_delta = None
            # Linear scan : OK pour < 10k points, 99% des cas
            for i, pt in enumerate(track.points):
                delta = abs((pt.timestamp - target).total_seconds())
                if best_delta is None or delta < best_delta:
                    best = (i, pt)
                    best_delta = delta
                elif delta > best_delta * 2 and best_delta < 60:
                    break  # on s'éloigne, optim

            if best is None or best_delta is None:
                continue
            if best_delta > self.tolerance.total_seconds():
                continue

            i, pt = best
            # Interpolation linéaire avec le voisin si possible
            if 0 < i < len(track.points) - 1:
                prev_pt = track.points[i - 1]
                next_pt = track.points[i + 1]
                # Choisir le voisin du bon côté
                if pt.timestamp > target and i > 0:
                    a, b = prev_pt, pt
                else:
                    a, b = pt, next_pt
                t_a = a.timestamp.timestamp()
                t_b = b.timestamp.timestamp()
                t_target = target.timestamp()
                if t_b > t_a:
                    ratio = max(0.0, min(1.0, (t_target - t_a) / (t_b - t_a)))
                    lat = a.lat + (b.lat - a.lat) * ratio
                    lon = a.lon + (b.lon - a.lon) * ratio
                    alt = None
                    if a.alt is not None and b.alt is not None:
                        alt = a.alt + (b.alt - a.alt) * ratio
                    return (lat, lon, alt)
            return (pt.lat, pt.lon, pt.alt)
        return None


# ── EXIF GPS write-back ──────────────────────────────────────────────────────

def _decimal_to_dms(deg: float) -> tuple:
    """Convertit un degré décimal en tuple EXIF (deg, min, sec) avec rationals."""
    abs_deg = abs(deg)
    d = int(abs_deg)
    m_full = (abs_deg - d) * 60
    m = int(m_full)
    s = (m_full - m) * 60
    # Rationals (numerator, denominator) — précision 1/10000 sur les secondes
    return ((d, 1), (m, 1), (int(s * 10000), 10000))


def write_gps_to_exif(photo_path: str, lat: float, lon: float,
                      alt: Optional[float] = None) -> bool:
    """
    Écrit GPS dans l'EXIF d'un JPEG. Retourne True si OK.
    /!\\ Modifie le fichier original — à utiliser avec précaution.
    """
    try:
        import piexif
    except ImportError:
        log.error("piexif non installé — pip install piexif")
        return False

    try:
        path = Path(photo_path)
        if not path.exists():
            return False
        if path.suffix.lower() not in (".jpg", ".jpeg"):
            log.debug("EXIF write skipped (non-JPEG): %s", path.name)
            return False

        try:
            exif_dict = piexif.load(str(path))
        except Exception:
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}

        gps_ifd = {
            piexif.GPSIFD.GPSLatitudeRef: ("N" if lat >= 0 else "S").encode(),
            piexif.GPSIFD.GPSLatitude:    _decimal_to_dms(lat),
            piexif.GPSIFD.GPSLongitudeRef: ("E" if lon >= 0 else "W").encode(),
            piexif.GPSIFD.GPSLongitude:   _decimal_to_dms(lon),
            piexif.GPSIFD.GPSVersionID:   (2, 3, 0, 0),
        }
        if alt is not None:
            alt_int = int(abs(alt) * 100)
            gps_ifd[piexif.GPSIFD.GPSAltitudeRef] = 0 if alt >= 0 else 1
            gps_ifd[piexif.GPSIFD.GPSAltitude] = (alt_int, 100)

        exif_dict["GPS"] = gps_ifd
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, str(path))
        log.info("GPS EXIF écrit dans %s : %.5f, %.5f", path.name, lat, lon)
        return True
    except Exception as e:
        log.error("EXIF write failed pour %s : %s", photo_path, e)
        return False
