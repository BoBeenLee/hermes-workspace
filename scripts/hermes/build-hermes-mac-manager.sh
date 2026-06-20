#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_NAME="HermesMacManager"
DISPLAY_NAME="Hermes Mac Manager"
SRC="$ROOT_DIR/apps/HermesMacManager/Sources/HermesMacManager/HermesMacManager.swift"
BUILD_DIR="$ROOT_DIR/artifacts/macos/$APP_NAME"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
INSTALL_DIR="${INSTALL_DIR:-$HOME/Applications}"
SWIFTC="${SWIFTC:-/usr/bin/swiftc}"

usage() {
  cat <<'USAGE'
Usage:
  scripts/hermes/build-hermes-mac-manager.sh [--install] [--launch]

Builds HermesMacManager.app without requiring an Xcode project.

Environment:
  INSTALL_DIR  App install destination for --install. Defaults to ~/Applications.
USAGE
}

install_app=false
launch_app=false

while (($#)); do
  case "$1" in
    --install)
      install_app=true
      ;;
    --launch)
      launch_app=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ ! -f "$SRC" ]]; then
  echo "missing source: $SRC" >&2
  exit 1
fi

if [[ ! -x "$SWIFTC" ]]; then
  echo "swift compiler not found: $SWIFTC" >&2
  exit 1
fi

rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS" "$APP_BUNDLE/Contents/Resources"

"$SWIFTC" \
  -O \
  -parse-as-library \
  -framework SwiftUI \
  -framework AppKit \
  "$SRC" \
  -o "$APP_BUNDLE/Contents/MacOS/$APP_NAME"

cat > "$APP_BUNDLE/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>$APP_NAME</string>
  <key>CFBundleIdentifier</key>
  <string>ai.hermes.mac-manager</string>
  <key>CFBundleName</key>
  <string>$DISPLAY_NAME</string>
  <key>CFBundleDisplayName</key>
  <string>$DISPLAY_NAME</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>0.1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
  <key>NSHumanReadableCopyright</key>
  <string>Hermes operator utility</string>
</dict>
</plist>
PLIST

codesign --force --deep --sign - "$APP_BUNDLE" >/dev/null

echo "built=$APP_BUNDLE"

if [[ "$install_app" == true ]]; then
  mkdir -p "$INSTALL_DIR"
  rm -rf "$INSTALL_DIR/$APP_NAME.app"
  cp -R "$APP_BUNDLE" "$INSTALL_DIR/$APP_NAME.app"
  echo "installed=$INSTALL_DIR/$APP_NAME.app"
fi

if [[ "$launch_app" == true ]]; then
  open "$INSTALL_DIR/$APP_NAME.app"
  echo "launched=$INSTALL_DIR/$APP_NAME.app"
fi
