#!/usr/bin/env bash
# Package dist/Wallcraft.app (from PyInstaller) as a drag-to-Applications disk image.
#
#   python -m PyInstaller --noconfirm wallcraft.spec
#   scripts/build_macos.sh            # names the DMG after this Mac's architecture
#
# Output: dist/Wallcraft-<version>-macos-arm64.dmg or -macos-intel.dmg
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/wallcraft/__init__.py)
case "$(uname -m)" in arm64) ARCH=arm64 ;; *) ARCH=intel ;; esac
APP=dist/Wallcraft.app
[ -d "$APP" ] || { echo "Build dist/Wallcraft.app first"; exit 1; }

# Ad-hoc signature: Apple Silicon refuses unsigned code entirely. This is not a Developer ID
# signature, so users still approve the app once (System Settings → Privacy & Security → Open Anyway).
codesign --force --deep --sign - "$APP"

STAGE=build/dmg
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "Wallcraft" -srcfolder "$STAGE" -ov -format UDZO "dist/Wallcraft-$VERSION-macos-$ARCH.dmg"
echo "Built dist/Wallcraft-$VERSION-macos-$ARCH.dmg"
