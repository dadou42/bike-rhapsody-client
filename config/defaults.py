"""
Valeurs par défaut de l'application.
"""
from pathlib import Path

APP_NAME = "Bike Rhapsody Client"
APP_BUNDLE_ID = "fr.bike-rhapsody.client"
GITHUB_REPO = "dadou42/bike-rhapsody-client"
GITHUB_RELEASES_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ASSET_NAME = "BikeRhapsodyClient-universal2.app.zip"

DEFAULT_SERVER_URL = "http://your-nas.local:8000"
DEFAULT_TIMEOUT = 15  # secondes

BUFFER_DIR = Path.home() / "BikeRhapsodyMediaBuffer"
CACHE_DIR = Path.home() / "Library" / "Caches" / "BikeRhapsodyClient"
DATA_DIR = Path.home() / "Library" / "Application Support" / "BikeRhapsodyClient"
DB_PATH = DATA_DIR / "client.db"

UPLOAD_CONCURRENCY = 2
RETRY_DELAYS = [30, 60, 300, 900, 3600]  # secondes
