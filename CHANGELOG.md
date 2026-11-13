# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.4] - 2026-11-13

### Changed
- Interface polish across the app: drawn icons replace text symbols (close, star, chevrons, add), the sidebar
  shows each layer's file type as a badge on its thumbnail along with the playback status, and the library grid
  fits two columns even at the smallest window size.
- The details panel shows a short prompt when nothing is selected instead of a column of disabled controls, and
  tags wallpapers that are currently in use.
- Better contrast in dark mode: text on accent-coloured buttons is now dark (5.7:1 instead of 3.2:1), and the
  animated tag keeps white text readable.
- Favourite stars sit on a dark disc so they stay visible on light images.

### Added
- Helpful empty states in the library: "No matches" with a *Clear search* button, and "No favorites here yet"
  with *Show all*.
- Keyboard navigation in the library grid shows a focus ring on the current tile.
- Screen-reader names for the search box and the display, fit and mode selectors.

### Fixed
- Clicking the same tile again after switching tabs now fills the details panel.
- Wrapped text in empty states and page headers no longer gets squeezed to its minimum width.

## [0.1.3] - 2026-11-13

### Changed
- **Two wallpaper layers.** Each monitor has a static layer (your regular Windows wallpaper) and an animated
  layer that plays on top. Setting an animated wallpaper no longer replaces your static wallpaper. When the
  animation is removed, or stopped by a battery or performance rule, your own static wallpaper is underneath.
- Changes to the static layer made while an animation covers it are applied once the animation stops. They're
  hidden anyway, and on Windows 11 24H2 they would disturb the video.
- Slideshow, time-of-day and theme modes change whichever layer matches the wallpaper they pick.

### Added
- Library is split into **Static** and **Animated** tabs, each with a count and its own empty-state hint, plus a
  Favorites filter.
- Every wallpaper shows its file type (JPG, PNG, MP4, WEBP, GIF…). Animated formats have a violet tag, and the
  details panel shows which layer it goes on.
- The sidebar shows both layers, with a button to remove the animated wallpaper. Also available from the tray
  menu and the library.

### Fixed
- The details panel no longer overlaps itself when the window is short (it now scrolls).

## [0.1.2] - 2026-11-13

### Changed
- **New live wallpaper engine, modelled on Lively Wallpaper.** Each live wallpaper now plays in its own
  [mpv](https://mpv.io) process, which Wallcraft places behind the desktop icons and controls remotely.
  Video decoding and drawing no longer happen inside Wallcraft's own window, which is what kept live
  wallpapers from showing on some systems.
- Desktop embedding follows Lively's handling of both desktop layouts, including Windows 11 24H2: the layout
  is detected from Explorer's window styles, and the icon/wallpaper stacking order is repaired whenever
  Explorer rebuilds its background layer.
- When switching to a live wallpaper, the old video is closed and the still frame is set *before* the new
  video is attached. Changing the static wallpaper while a video is attached breaks it on 24H2.

### Added
- mpv is bundled with every build (downloaded and checksum-verified by `scripts/fetch_mpv.py`).
- Player processes are tied to Wallcraft with a Windows job object, so they never keep running after
  Wallcraft exits or crashes.
- Crashed or detached players restart automatically. A file mpv can't play falls back to the built-in player.

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
