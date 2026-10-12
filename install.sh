#!/usr/bin/env bash
# One-click installer for the wechat-self-analysis WorkBuddy skill (macOS / Linux).
# Usage:
#   curl -fsSL https://github.com/hwdemtv/wechat-self-analysis/raw/main/install.sh | bash
set -euo pipefail

OWNER="hwdemtv"
NAME="wechat-self-analysis"
URL="https://github.com/$OWNER/$NAME/archive/refs/heads/main.zip"

TMP="$(mktemp -d)"
SKILLS_DIR="${WORKBUDDY_SKILLS_DIR:-$HOME/.workbuddy/skills}"
DEST="$SKILLS_DIR/$NAME"

cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

echo "==> Downloading $URL"
curl -fsSL "$URL" -o "$TMP/$NAME.zip"

echo "==> Extracting into $SKILLS_DIR"
mkdir -p "$SKILLS_DIR"
unzip -oq "$TMP/$NAME.zip" -d "$TMP"
rm -rf "$DEST"
mv "$TMP/$NAME-main" "$DEST"

echo "==> Installed: $DEST"
if command -v python3 >/dev/null 2>&1; then
  echo "==> Running dependency check (scripts/install_deps.py)"
  (cd "$DEST" && python3 scripts/install_deps.py) || true
else
  echo "==> python3 not found; run 'python3 scripts/install_deps.py' inside $DEST later."
fi

echo "==> Done. Restart WorkBuddy to load the skill."
