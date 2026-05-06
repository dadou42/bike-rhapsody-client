"""
Client HTTP de base — httpx synchrone, gestion de session cookie.
"""
import httpx
from config.defaults import DEFAULT_TIMEOUT
from logs.logger import get_logger

log = get_logger("api.client")


class BRClient:
    """Client HTTP vers l'API Bike Rhapsody."""

    def __init__(self, base_url: str, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session_cookie: str | None = None
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=True,
        )

    # ── Auth cookie ──────────────────────────────────────────────────────────

    @property
    def is_authenticated(self) -> bool:
        return bool(self._session_cookie)

    def set_session_cookie(self, cookie: str) -> None:
        self._session_cookie = cookie
        self._http.cookies.set("session", cookie)
        log.debug("Session cookie set")

    def clear_session(self) -> None:
        self._session_cookie = None
        self._http.cookies.clear()
        log.debug("Session cleared")

    # ── HTTP verbs ────────────────────────────────────────────────────────────

    def get(self, path: str, **kwargs) -> httpx.Response:
        log.debug("GET %s", path)
        return self._http.get(path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        log.debug("POST %s", path)
        return self._http.post(path, **kwargs)

    def put(self, path: str, **kwargs) -> httpx.Response:
        log.debug("PUT %s", path)
        return self._http.put(path, **kwargs)

    def delete(self, path: str, **kwargs) -> httpx.Response:
        log.debug("DELETE %s", path)
        return self._http.delete(path, **kwargs)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Vérifie que le serveur est accessible."""
        try:
            r = self._http.get("/api/sync/releases/fast-status", timeout=5)
            return r.status_code < 500
        except Exception as e:
            log.warning("Ping failed: %s", e)
            return False

    def get_server_version(self) -> str | None:
        try:
            r = self._http.get("/api/version", timeout=5)
            if r.status_code == 200:
                return r.json().get("version")
        except Exception:
            pass
        return None

    def close(self) -> None:
        self._http.close()


# Singleton partagé — initialisé par bootstrap
_client: BRClient | None = None


def get_client() -> BRClient:
    if _client is None:
        raise RuntimeError("Client not initialized — call init_client() first")
    return _client


def init_client(base_url: str, timeout: int = DEFAULT_TIMEOUT) -> BRClient:
    global _client
    if _client:
        _client.close()
    _client = BRClient(base_url, timeout)
    log.info("HTTP client initialized → %s", base_url)
    return _client
