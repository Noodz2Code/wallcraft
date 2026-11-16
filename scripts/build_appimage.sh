#!/usr/bin/env bash
# Package the PyInstaller folder build (dist/Wallcraft) as an AppImage and a tar.gz.
#
#   WALLCRAFT_ONEFILE=0 WALLCRAFT_REQUIRE_XCB_CURSOR=1 python -m PyInstaller --noconfirm wallcraft.spec
#   scripts/build_appimage.sh
#
# Output: dist/Wallcraft-<version>-x86_64.AppImage and dist/Wallcraft-<version>-linux-x86_64.tar.gz
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/wallcraft/__init__.py)
DIST=dist
APPDIR=build/AppDir
TOOL=build/appimagetool-x86_64.AppImage
TOOL_URL=https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage

[ -x "$DIST/Wallcraft/Wallcraft" ] || { echo "Build dist/Wallcraft first (WALLCRAFT_ONEFILE=0)"; exit 1; }

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$DIST/Wallcraft" "$APPDIR/usr/lib/wallcraft"
cp packaging/linux/wallcraft.desktop "$APPDIR/wallcraft.desktop"
cp packaging/linux/wallcraft.desktop "$APPDIR/usr/share/applications/"
cp src/wallcraft/resources/icon.png "$APPDIR/wallcraft.png"
cp src/wallcraft/resources/icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/wallcraft.png"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/wallcraft/Wallcraft" "$@"
RUN
chmod +x "$APPDIR/AppRun"

if [ ! -x "$TOOL" ]; then
    mkdir -p build
    curl -fsSL -o "$TOOL" "$TOOL_URL"
    chmod +x "$TOOL"
fi
# --appimage-extract-and-run: works without FUSE (e.g. on CI machines and in containers).
ARCH=x86_64 "$TOOL" --appimage-extract-and-run --no-appstream "$APPDIR" "$DIST/Wallcraft-$VERSION-x86_64.AppImage"

tar -czf "$DIST/Wallcraft-$VERSION-linux-x86_64.tar.gz" -C "$DIST" Wallcraft
echo "Built $DIST/Wallcraft-$VERSION-x86_64.AppImage and $DIST/Wallcraft-$VERSION-linux-x86_64.tar.gz"
