# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.1] - 2026-11-13

### Added
- Many more video formats: M4V, ASF, MPG/MPEG, M2V, VOB, TS, M2TS, MTS, FLV, F4V, 3GP, 3G2 and OGV.
- Animated WebP files now play as live wallpapers (still WebP images stay normal wallpapers).
- Library badges show the animated format (GIF / WEBP).

### Changed
- `.ts` files are only added to the library when they are real video, not TypeScript source code.
- CI and release workflows use the Node.js 24 versions of their GitHub Actions.

### Fixed
- Starting the release workflow by hand now creates a draft release instead of failing.

## [0.1.0] - 2026-11-13

### Added
- Wallpaper library with folder scanning, search, filters, favourites and drag-and-drop.
- Per-monitor wallpapers and all Windows fit modes (fill, fit, stretch, center, tile, span).
- Live wallpapers: videos (MP4, WebM, MKV, MOV, AVI, WMV) and animated GIFs rendered behind the desktop icons.
- Slideshow mode with interval, shuffle and custom playlists.
- Time-of-day mode with fixed times or sun-based triggers (dawn, sunrise, solar noon, sunset, dusk), calculated offline.
- Theme sync: separate light and dark wallpapers that follow Windows' colour mode.
- Automatic Windows light/dark switching by sunrise/sunset or custom times.
- Performance rules that pause or stop live wallpapers on battery, low battery, battery saver,
  fullscreen apps, maximized windows and when the screen is locked.
- System tray menu, start with Windows, single-instance handling and a portable mode.
- Installer, portable exe and zip builds published by GitHub Actions.
