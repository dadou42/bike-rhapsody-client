"""
Logging centralisé — Bike Rhapsody Mac Client
"""
import logging
import logging.handlers
import os
from pathlib import Path


def get_log_dir() -> Path:
    log_dir = Path.home() / "Library" / "Logs" / "BikeRhapsodyClient"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging(level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    log_file = get_log_dir() / "client.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotation : 5 MB × 5 fichiers
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(log_level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"br_client.{name}")


def get_log_file_path() -> Path:
    return get_log_dir() / "client.log"
