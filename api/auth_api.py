"""
Authentification Bike Rhapsody — login / logout / vérification session.
"""
from dataclasses import dataclass
from api.client import get_client
from security.keychain import save_token, load_token, delete_token, save_credentials, load_credentials
from logs.logger import get_logger

log = get_logger("api.auth")


@dataclass
class AuthResult:
    success: bool
    message: str = ""
    username: str = ""


def login(username: str, password: str, profile_name: str = "default") -> AuthResult:
    """Authentifie l'utilisateur et stocke le cookie de session dans le Keychain."""
    client = get_client()
    try:
        r = client.post(
            "/api/auth/login",
            json={"email": username, "password": password},
        )
        if r.status_code == 200:
            # Récupérer le cookie de session
            cookie = r.cookies.get("session") or r.cookies.get("br_session")
            if not cookie:
                # Certaines versions BR utilisent un token JSON
                data = r.json()
                cookie = data.get("token") or data.get("access_token")

            if cookie:
                client.set_session_cookie(cookie)
                save_token(profile_name, cookie)
                save_credentials(profile_name, username, password)
                log.info("Login OK for '%s' on profile '%s'", username, profile_name)
                return AuthResult(success=True, username=username)
            else:
                log.warning("Login OK but no session cookie found in response")
                return AuthResult(success=False, message="Pas de cookie de session dans la réponse")

        elif r.status_code == 401:
            return AuthResult(success=False, message="Email ou mot de passe incorrect")
        else:
            return AuthResult(success=False, message=f"Erreur serveur HTTP {r.status_code}")

    except Exception as e:
        log.error("Login exception: %s", e)
        return AuthResult(success=False, message=f"Connexion impossible : {e}")


def restore_session(profile_name: str = "default") -> bool:
    """Restaure la session depuis le Keychain si disponible."""
    token = load_token(profile_name)
    if not token:
        return False
    client = get_client()
    client.set_session_cookie(token)
    # Vérifie que le token est encore valide
    try:
        r = client.get("/api/activities/stats/timeline")
        if r.status_code == 401:
            log.info("Stored token expired for profile '%s'", profile_name)
            client.clear_session()
            delete_token(profile_name)
            return False
        log.info("Session restored for profile '%s'", profile_name)
        return True
    except Exception as e:
        log.warning("Session restore check failed: %s", e)
        # Garder le cookie quand même (peut être hors ligne)
        return True


def logout(profile_name: str = "default") -> None:
    client = get_client()
    try:
        client.post("/api/auth/logout")
    except Exception:
        pass
    client.clear_session()
    delete_token(profile_name)
    log.info("Logged out from profile '%s'", profile_name)


def get_current_user() -> dict | None:
    """Récupère les infos de l'utilisateur connecté."""
    client = get_client()
    try:
        r = client.get("/api/auth/me")
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.warning("get_current_user failed: %s", e)
    return None
