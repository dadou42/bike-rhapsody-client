# 🚴 Bike Rhapsody — Client Mac

Application macOS native (PySide6) pour administrer un serveur Bike Rhapsody auto-hébergé : import de médias (photos/vidéos GoPro + FIT), enrichissement GPS depuis les traces FIT, upload vers le serveur, matching automatique aux activités Strava.

[![Latest release](https://img.shields.io/github/v/release/dadou42/bike-rhapsody-client?label=release)](https://github.com/dadou42/bike-rhapsody-client/releases/latest)
[![Universal](https://img.shields.io/badge/macOS-Intel%20%2B%20Apple%20Silicon-blue)](#installation)

---

## ✨ Fonctionnalités

- 🔐 **Authentification** : login email/mot de passe + 2FA TOTP, session persistante via Keychain (avec fallback fichier chiffré)
- 📥 **Import médias** : drag & drop fichiers/dossiers, scan récursif, dédup SHA256 locale + serveur, miniatures Pillow + ffmpeg
- 🛰 **Enrichissement GPS** depuis FIT/GPX : interpolation linéaire des coordonnées GPS sur les photos par horodatage EXIF, optionnellement réécriture EXIF
- 📤 **Upload résilient** : file d'attente persistante SQLite, retry exponentiel (30s → 1h), reprise après reconnexion
- 🚴 **Matching activités** : auto-association des médias orphelins à leur activité par `captured_at ∈ [start, start + elapsed]` avec tolérance configurable, drag & drop manuel
- 📡 **Watching dossier** : surveillance d'un dossier (carte SD, Dropbox local) avec détection de stabilité fichier (3s)
- 🔄 **Auto-update** via GitHub Releases : check au démarrage, download + self-replace bash, redémarrage transparent

---

## 📦 Installation

### Pour les utilisateurs

Télécharge le `.zip` depuis la [dernière release](https://github.com/dadou42/bike-rhapsody-client/releases/latest), décompresse, et glisse `BikeRhapsodyClient.app` dans `/Applications`.

Au premier lancement, autorise l'app dans **Réglages → Confidentialité et sécurité** (signature ad-hoc).

### Première configuration

1. Lance l'app → onglet **Paramètres**
2. URL du serveur Bike Rhapsody (ex: `http://nas.local:8000`) → **Tester la connexion**
3. **Enregistrer le profil**
4. Saisis ton email / mot de passe → **Se connecter**
5. Si la 2FA est activée, le code TOTP est demandé dans une fenêtre dédiée

---

## 🛠 Compilation depuis les sources

### Pré-requis

- Python 3.13+
- macOS 13+
- ffmpeg (pour les miniatures vidéo)

### Build local

```bash
git clone https://github.com/dadou42/bike-rhapsody-client.git
cd bike-rhapsody-client
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Build de dev (architecture native, plus rapide)
./build.sh --dev

# Build de production (universal2 — Intel + Apple Silicon)
./build.sh
```

L'app résultante est dans `dist/BikeRhapsodyClient.app` et l'archive de distribution dans `dist/BikeRhapsodyClient-universal2.app.zip`.

---

## 🏗 Architecture

```
api/            ← Client HTTP httpx (auth, media, matching, updater)
app/            ← Bootstrap, état partagé QObject (signals)
config/         ← Defaults, settings dataclass
logs/           ← Logger rotatif (~/Library/Logs/BikeRhapsodyClient/)
media/          ← Scanner, checksum, EXIF/ffprobe, dédup, FIT enricher, miniatures
security/       ← Keychain macOS + fallback fichier chiffré XOR/SHA256
storage/        ← SQLite local (6 tables, migrations versionnées)
sync/           ← Worker QThread d'upload avec retry exponentiel
ui/             ← QMainWindow + QStackedWidget + 9 vues
updater/        ← Auto-update via GitHub Releases API
watchers/       ← Folder watching watchdog avec stabilité 3s
```

### Flux de données

```
Fichier sur disque
    ↓ (drag&drop ou folder watch)
Scanner → checksum SHA256 + EXIF + thumbnail → DB locale (status='ready')
    ↓
[optionnel] FitEnricher → backfill GPS depuis FIT par captured_at
    ↓
Upload Queue (SQLite) → Worker QThread → POST /api/media/upload (multipart)
    ↓
orphan_media côté serveur (sha256 unique par user)
    ↓
[user déclenche] POST /api/media/match-orphans
    ↓
Liaison à l'activité par captured_at ∈ [start, start + elapsed + tolerance]
    ↓
Affichage dans la galerie de l'activité (webapp BR)
```

---

## 🔒 Sécurité

- Pas de stockage en clair des mots de passe (Keychain ou fichier chiffré)
- Cookie de session HTTP-only via httpx
- Vérification SHA256 côté serveur (mismatch = rejet)
- Aucun token stocké dans le code source

---

## 🤝 Contribuer

Issues et PR bienvenues sur https://github.com/dadou42/bike-rhapsody-client/issues

---

## 📜 Licence

MIT — voir [LICENSE](LICENSE)
