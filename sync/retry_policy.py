"""
Politique de retry exponentielle pour les uploads échoués.
"""
from datetime import datetime, timedelta
from config.defaults import RETRY_DELAYS
from logs.logger import get_logger

log = get_logger("sync.retry")

MAX_RETRIES = len(RETRY_DELAYS)


def next_retry_at(retry_count: int) -> str | None:
    """
    Retourne l'heure ISO du prochain essai, ou None si max atteint.
    """
    if retry_count >= MAX_RETRIES:
        return None
    delay = RETRY_DELAYS[min(retry_count, len(RETRY_DELAYS) - 1)]
    next_dt = datetime.now() + timedelta(seconds=delay)
    return next_dt.isoformat()


def should_retry(retry_count: int, next_retry_iso: str | None) -> bool:
    if retry_count >= MAX_RETRIES:
        return False
    if not next_retry_iso:
        return True
    try:
        next_dt = datetime.fromisoformat(next_retry_iso)
        return datetime.now() >= next_dt
    except Exception:
        return False


def retry_delay_label(retry_count: int) -> str:
    if retry_count >= MAX_RETRIES:
        return "Abandon"
    delay = RETRY_DELAYS[min(retry_count, len(RETRY_DELAYS) - 1)]
    if delay < 60:
        return f"{delay}s"
    if delay < 3600:
        return f"{delay // 60}min"
    return f"{delay // 3600}h"
