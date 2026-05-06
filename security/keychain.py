"""
Stockage sécurisé des credentials dans le Keychain macOS via keyring.
"""
import keyring
from logs.logger import get_logger

log = get_logger("keychain")

SERVICE = "BikeRhapsodyClient"


def save_credentials(profile_name: str, username: str, password: str) -> None:
    key = f"{profile_name}:{username}"
    keyring.set_password(SERVICE, key, password)
    log.info("Credentials saved for profile '%s' user '%s'", profile_name, username)


def load_credentials(profile_name: str, username: str) -> str | None:
    key = f"{profile_name}:{username}"
    return keyring.get_password(SERVICE, key)


def save_token(profile_name: str, token: str) -> None:
    keyring.set_password(SERVICE, f"token:{profile_name}", token)
    log.debug("Token saved for profile '%s'", profile_name)


def load_token(profile_name: str) -> str | None:
    return keyring.get_password(SERVICE, f"token:{profile_name}")


def delete_token(profile_name: str) -> None:
    try:
        keyring.delete_password(SERVICE, f"token:{profile_name}")
        log.info("Token deleted for profile '%s'", profile_name)
    except keyring.errors.PasswordDeleteError:
        pass


def delete_credentials(profile_name: str, username: str) -> None:
    try:
        keyring.delete_password(SERVICE, f"{profile_name}:{username}")
    except keyring.errors.PasswordDeleteError:
        pass
