"""
Authentification Bike Rhapsody — login / 2FA / logout / restauration session.

Flux 2FA :
  1. POST /login  (form: email, password)  follow_redirects=False
     → 302 vers /login/2fa  + Set-Cookie: PENDING_2FA_COOKIE=<token>
  2. POST /login/2fa  (form: code, pending_token_form=<token>)
     → 302 vers /  + Set-Cookie: session=<cookie>
"""
from dataclasses import dataclass, field
from api.client import get_client
from security.keychain import save_token, load_token, delete_token, save_credentials, load_credentials
from logs.logger import get_logger

log = get_logger("api.auth")

# Noms possibles du cookie de session principale
_SESSION_NAMES = ["session", "br_session", "SESSION", "br_auth", "flask_session"]
# Noms possibles du cookie pending 2FA (l'un d'eux sera présent selon la version BR)
_PENDING_NAMES = [
    "PENDING_2FA_COOKIE", "pending_2fa_token", "pending_token",
    "_2fa_pending", "br_pending_2fa", "2fa_pending",
]


@dataclass
class AuthResult:
    success: bool
    message: str = ""
    username: str = ""
    # 2FA
    needs_2fa: bool = False
    pending_token: str = ""      # valeur du cookie PENDING_2FA_COOKIE
    pending_cookie_name: str = ""  # nom réel du cookie (pour debug)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _first_cookie(cookies, names: list[str]) -> tuple[str, str]:
    """Retourne (nom, valeur) du premier cookie trouvé parmi names, sinon ('','')."""
    for name in names:
        val = cookies.get(name)
        if val:
            return name, val
    # Fallback : chercher par sous-chaîne dans tous les cookies
    for cname, cval in cookies.items():
        cname_lower = cname.lower()
        for target in names:
            if target.lower() in cname_lower or cname_lower in target.lower():
                return cname, cval
    return "", ""


def _extract_session(response, client_cookies: dict) -> str:
    """Extrait le cookie de session depuis la réponse OU le jar du client (dict)."""
    # 1. Depuis la réponse directe
    _, val = _first_cookie(response.cookies, _SESSION_NAMES)
    if val:
        return val
    # 2. Depuis le jar du client (passé en tant que dict via client.cookies_dict())
    _, val = _first_cookie(client_cookies, _SESSION_NAMES)
    return val


# ── Login étape 1 ────────────────────────────────────────────────────────────

def login(username: str, password: str, profile_name: str = "default") -> AuthResult:
    """
    Étape 1 : POST /login en form-data.
    - Succès direct  → AuthResult(success=True)
    - 2FA requise    → AuthResult(needs_2fa=True, pending_token=...)
    - Échec          → AuthResult(success=False, message=...)
    """
    client = get_client()
    try:
        r = client.post(
            "/login",
            data={"email": username, "password": password},
            follow_redirects=False,
        )
        log.debug("POST /login → HTTP %s  Location: %s", r.status_code,
                  r.headers.get("location", "—"))

        # ── 2FA : redirect vers /login/2fa ──────────────────────────────────
        if r.status_code in (301, 302, 303, 307, 308):
            location = r.headers.get("location", "")
            if "/login/2fa" in location or "/2fa" in location:
                cname, pending = _first_cookie(r.cookies, _PENDING_NAMES)
                if not pending:
                    # Certaines versions BR mettent le token dans le corps JSON
                    try:
                        pending = r.json().get("pending_token", "")
                    except Exception:
                        pass
                if not pending:
                    log.warning("2FA redirect détecté mais aucun pending token trouvé")
                save_credentials(profile_name, username, password)
                log.info("2FA requise pour '%s' (cookie: %s)", username, cname or "inconnu")
                return AuthResult(
                    success=False,
                    needs_2fa=True,
                    pending_token=pending,
                    pending_cookie_name=cname,
                    message="Double authentification requise",
                )

            # Redirect vers autre chose (/, /dashboard…) = login réussi sans 2FA
            session = _extract_session(r, client.cookies_dict())
            if session:
                client.set_session_cookie(session)
                save_token(profile_name, session)
                save_credentials(profile_name, username, password)
                log.info("Login OK (redirect) pour '%s'", username)
                return AuthResult(success=True, username=username)

            # Pas de cookie dans la réponse 302 → suivre le redirect pour le récupérer
            r2 = client.get(location or "/")
            session = _extract_session(r2, client.cookies_dict())
            if session:
                client.set_session_cookie(session)
                save_token(profile_name, session)
                save_credentials(profile_name, username, password)
                log.info("Login OK (post-redirect) pour '%s'", username)
                return AuthResult(success=True, username=username)
            return AuthResult(success=False, message="Connecté mais cookie de session introuvable")

        # ── Réponse directe 200 (rare) ──────────────────────────────────────
        elif r.status_code == 200:
            session = _extract_session(r, client.cookies_dict())
            if session:
                client.set_session_cookie(session)
                save_token(profile_name, session)
                save_credentials(profile_name, username, password)
                log.info("Login OK (200) pour '%s'", username)
                return AuthResult(success=True, username=username)
            # Peut-être un token JSON
            try:
                data = r.json()
                token = data.get("token") or data.get("access_token") or data.get("session")
                if token:
                    client.set_session_cookie(token)
                    save_token(profile_name, token)
                    save_credentials(profile_name, username, password)
                    return AuthResult(success=True, username=username)
            except Exception:
                pass
            return AuthResult(success=False, message="Réponse inattendue du serveur")

        elif r.status_code in (401, 403):
            return AuthResult(success=False, message="Email ou mot de passe incorrect")

        elif r.status_code == 422:
            return AuthResult(success=False, message="Données de connexion invalides")

        else:
            return AuthResult(success=False, message=f"Erreur serveur HTTP {r.status_code}")

    except Exception as e:
        log.error("Login exception: %s", e)
        return AuthResult(success=False, message=f"Connexion impossible : {e}")


# ── Login étape 2 : TOTP ────────────────────────────────────────────────────

def login_2fa(code: str, pending_token: str,
              profile_name: str = "default") -> AuthResult:
    """
    Étape 2 : POST /login/2fa avec le code TOTP et le pending_token.
    Le pending_token est la valeur du cookie PENDING_2FA_COOKIE.
    """
    client = get_client()
    try:
        r = client.post(
            "/login/2fa",
            data={"code": code.strip(), "pending_token_form": pending_token},
            follow_redirects=True,   # suivre jusqu'à la page finale pour récupérer le cookie
        )
        log.debug("POST /login/2fa → HTTP %s", r.status_code)

        session = _extract_session(r, client.cookies_dict())
        if session:
            client.set_session_cookie(session)
            save_token(profile_name, session)
            creds = load_credentials(profile_name)
            username = creds[0] if creds else ""
            log.info("2FA OK pour profil '%s'", profile_name)
            return AuthResult(success=True, username=username)

        if r.status_code in (400, 401, 422):
            return AuthResult(success=False, message="Code incorrect ou expiré")

        if r.status_code >= 500:
            return AuthResult(success=False, message=f"Erreur serveur HTTP {r.status_code}")

        # Pas de cookie trouvé malgré un statut OK
        log.warning("2FA : réponse HTTP %s mais aucun cookie de session", r.status_code)
        return AuthResult(success=False,
                          message="Code accepté mais cookie de session introuvable")

    except Exception as e:
        log.error("2FA exception: %s", e)
        return AuthResult(success=False, message=f"Erreur 2FA : {e}")


# ── Restauration de session ──────────────────────────────────────────────────

def restore_session(profile_name: str = "default") -> bool:
    """Restaure la session depuis le Keychain si disponible."""
    token = load_token(profile_name)
    if not token:
        return False
    client = get_client()
    client.set_session_cookie(token)
    try:
        r = client.get("/api/activities/stats/timeline")
        if r.status_code == 401:
            log.info("Token expiré pour profil '%s'", profile_name)
            client.clear_session()
            delete_token(profile_name)
            return False
        log.info("Session restaurée pour profil '%s'", profile_name)
        return True
    except Exception as e:
        log.warning("Vérification de session échouée : %s (on garde le token)", e)
        return True   # Hors ligne → on garde le cookie


# ── Logout ────────────────────────────────────────────────────────────────────

def logout(profile_name: str = "default") -> None:
    client = get_client()
    try:
        client.post("/logout")
    except Exception:
        pass
    try:
        client.post("/api/auth/logout")
    except Exception:
        pass
    client.clear_session()
    delete_token(profile_name)
    log.info("Déconnecté du profil '%s'", profile_name)


# ── Infos utilisateur ────────────────────────────────────────────────────────

def get_current_user() -> dict | None:
    """Récupère les infos de l'utilisateur connecté."""
    client = get_client()
    for path in ("/api/auth/me", "/api/me", "/api/user/profile"):
        try:
            r = client.get(path)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                continue
        except Exception as e:
            log.warning("get_current_user (%s) : %s", path, e)
    return None
