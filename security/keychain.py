"""
Stockage sécurisé des credentials et tokens.

Stratégie :
  1. Tente Keychain macOS (via `keyring`) — sécurisé, géré par macOS
  2. Si le Keychain refuse (app non signée, erreur -67030, etc.) → fallback
     sur un fichier chiffré dans ~/Library/Application Support/BikeRhapsodyClient/
     (clé dérivée du hostname + username, pas de la sécurité forte mais
      au moins le fichier n'est pas en clair sur le disque)

Toutes les fonctions sont non-bloquantes : un échec de stockage logue un
warning mais ne lève pas d'exception.
"""
import json
import os
import base64
import hashlib
import getpass
import platform
from pathlib import Path

import keyring
import keyring.errors

from logs.logger import get_logger

log = get_logger("keychain")

SERVICE = "BikeRhapsodyClient"


def _data_dir() -> Path:
    p = Path.home() / "Library" / "Application Support" / SERVICE
    p.mkdir(parents=True, exist_ok=True)
    return p


def _fallback_file() -> Path:
    return _data_dir() / "secrets.dat"


def _xor_key() -> bytes:
    """Clé d'obfuscation dérivée de host+user — pas du chiffrement fort,
    mais empêche les secrets d'apparaître en clair."""
    seed = f"{platform.node()}|{getpass.getuser()}|BikeRhapsody2026".encode()
    return hashlib.sha256(seed).digest()


def _xor(data: bytes) -> bytes:
    key = _xor_key()
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _fallback_load() -> dict:
    f = _fallback_file()
    if not f.exists():
        return {}
    try:
        raw = base64.b64decode(f.read_bytes())
        plain = _xor(raw)
        return json.loads(plain.decode("utf-8"))
    except Exception as e:
        log.warning("Fallback secrets read failed: %s", e)
        return {}


def _fallback_save(data: dict) -> None:
    try:
        plain = json.dumps(data).encode("utf-8")
        enc = base64.b64encode(_xor(plain))
        f = _fallback_file()
        f.write_bytes(enc)
        try:
            os.chmod(f, 0o600)
        except Exception:
            pass
    except Exception as e:
        log.error("Fallback secrets write failed: %s", e)


# ── Helpers Keychain avec fallback ─────────────────────────────────────────────

def _kr_set(account: str, value: str) -> bool:
    """Tente Keychain, fallback fichier. Retourne True si stocké quelque part."""
    try:
        keyring.set_password(SERVICE, account, value)
        return True
    except Exception as e:
        log.warning("Keychain set failed for '%s' (%s) — fallback fichier", account, e)
        data = _fallback_load()
        data[account] = value
        _fallback_save(data)
        return True


def _kr_get(account: str) -> str | None:
    try:
        v = keyring.get_password(SERVICE, account)
        if v is not None:
            return v
    except Exception as e:
        log.warning("Keychain get failed for '%s' (%s) — fallback fichier", account, e)
    return _fallback_load().get(account)


def _kr_del(account: str) -> None:
    try:
        keyring.delete_password(SERVICE, account)
    except keyring.errors.PasswordDeleteError:
        pass
    except Exception as e:
        log.debug("Keychain delete failed for '%s' (%s)", account, e)
    data = _fallback_load()
    if account in data:
        del data[account]
        _fallback_save(data)


# ── API publique ─────────────────────────────────────────────────────────────

def save_credentials(profile_name: str, username: str, password: str) -> None:
    """Stocke email+password sous forme JSON pour le profil donné."""
    blob = json.dumps({"username": username, "password": password})
    if _kr_set(f"creds:{profile_name}", blob):
        log.info("Credentials stockés pour profil '%s' user '%s'", profile_name, username)


def load_credentials(profile_name: str) -> tuple[str, str] | None:
    """Retourne (username, password) ou None."""
    blob = _kr_get(f"creds:{profile_name}")
    if not blob:
        return None
    try:
        d = json.loads(blob)
        return d.get("username", ""), d.get("password", "")
    except Exception:
        return None


def save_token(profile_name: str, token: str) -> None:
    if _kr_set(f"token:{profile_name}", token):
        log.debug("Token stocké pour profil '%s'", profile_name)


def load_token(profile_name: str) -> str | None:
    return _kr_get(f"token:{profile_name}")


def delete_token(profile_name: str) -> None:
    _kr_del(f"token:{profile_name}")
    log.info("Token supprimé pour profil '%s'", profile_name)


def delete_credentials(profile_name: str) -> None:
    _kr_del(f"creds:{profile_name}")
