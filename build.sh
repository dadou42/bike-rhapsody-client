#!/bin/bash
# =============================================================================
# Bike Rhapsody Mac Client — Build universel (Intel + Apple Silicon)
# Usage : ./build.sh [--dev]
#
# Produit : dist/BikeRhapsodyClient.app  (universal2 = Intel + Silicon)
#           dist/BikeRhapsodyClient-universal2.app.zip  (pour auto-update)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $*"; }
info() { echo -e "${BLUE}ℹ${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; exit 1; }

VERSION=$(python3 -c "import json; print(json.load(open('version.json'))['version'])")
APP_NAME="BikeRhapsodyClient"

# Mode dev (--dev) = build natif seulement, plus rapide, pas de contrainte fat binary
DEV_MODE=0
for arg in "$@"; do [[ "$arg" == "--dev" ]] && DEV_MODE=1; done

if [[ $DEV_MODE -eq 1 ]]; then
    TARGET_ARCH=""
    info "Building Bike Rhapsody Client v${VERSION} (native — dev mode)"
else
    TARGET_ARCH="--target-arch universal2"
    info "Building Bike Rhapsody Client v${VERSION} (universal2)"
fi

# ── Prérequis ─────────────────────────────────────────────────────────────────
command -v python3 >/dev/null   || fail "python3 not found"
command -v pyinstaller >/dev/null 2>&1 || pip3 install pyinstaller

# ── Venv ─────────────────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    info "Creating venv…"
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt pyinstaller

# ── Nettoyage ─────────────────────────────────────────────────────────────────
rm -rf build/ dist/

# ── Build ──────────────────────────────────────────────────────────────────────
info "Running PyInstaller…"
pyinstaller \
    --noconfirm \
    --windowed \
    --name "$APP_NAME" \
    $TARGET_ARCH \
    --add-data "version.json:." \
    --add-data "assets:assets" \
    --hidden-import PySide6.QtCore \
    --hidden-import PySide6.QtWidgets \
    --hidden-import PySide6.QtGui \
    --hidden-import keyring.backends.macOS \
    --hidden-import keyring.backends.fail \
    main.py

APP_PATH="dist/${APP_NAME}.app"

if [ ! -d "$APP_PATH" ]; then
    fail ".app bundle not found after build"
fi
ok "Bundle created: $APP_PATH"

# ── Info.plist macOS ──────────────────────────────────────────────────────────
PLIST="$APP_PATH/Contents/Info.plist"
if [ -f "$PLIST" ]; then
    # Remplacer la version dans Info.plist
    /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$PLIST" 2>/dev/null || true
    /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$PLIST" 2>/dev/null || true
    # Bundle ID stable (nécessaire pour Keychain)
    /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.bikerhapsody.client" "$PLIST" 2>/dev/null \
        || /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string com.bikerhapsody.client" "$PLIST" 2>/dev/null || true
    ok "Info.plist version=$VERSION, bundle=com.bikerhapsody.client"
fi

# ── Codesign ad-hoc (nécessaire pour Keychain access) ─────────────────────────
info "Re-signing bundle (deep, ad-hoc) for Keychain access…"
codesign --force --deep --sign - --timestamp=none \
    --options=runtime \
    --entitlements <(cat <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.cs.allow-unsigned-executable-memory</key><true/>
    <key>com.apple.security.cs.allow-jit</key><true/>
    <key>com.apple.security.cs.disable-library-validation</key><true/>
    <key>keychain-access-groups</key><array><string>com.bikerhapsody.client</string></array>
</dict>
</plist>
PLIST
) "$APP_PATH" 2>&1 | tail -5 || warn "codesign avec entitlements a échoué, fallback simple ad-hoc"

# Fallback : ad-hoc simple si la commande ci-dessus a échoué
codesign --force --deep --sign - "$APP_PATH" 2>/dev/null || true
ok "Bundle signé"

# Vérification
if codesign --verify --deep --strict "$APP_PATH" 2>/dev/null; then
    ok "Signature valide"
else
    warn "Signature non standard (normal pour ad-hoc)"
fi

# ── Archive pour auto-update ──────────────────────────────────────────────────
ZIP_NAME="${APP_NAME}-universal2.app.zip"
cd dist
zip -r -q "$ZIP_NAME" "${APP_NAME}.app"
cd "$SCRIPT_DIR"
ok "Archive: dist/${ZIP_NAME} ($(du -sh "dist/${ZIP_NAME}" | cut -f1))"

# ── Résumé ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✓ Build v${VERSION} terminé${NC}"
echo -e "${GREEN}  .app   → dist/${APP_NAME}.app${NC}"
echo -e "${GREEN}  .zip   → dist/${ZIP_NAME}${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo ""
info "Pour tester : open dist/${APP_NAME}.app"
info "Pour publier : créer une release GitHub et uploader dist/${ZIP_NAME}"
