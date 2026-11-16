<p align="center">
  <img src="src/wallcraft/resources/icon-512.png" width="96" alt="Wallcraft icon">
</p>

<h1 align="center">Wallcraft</h1>

<p align="center">
  A free, open-source wallpaper manager for Windows, Linux and macOS: live video wallpapers,
  wallpapers that follow the time of day, and light/dark theme sync.
</p>

<p align="center">
  <a href="../../releases/latest"><strong>Download</strong></a> ·
  <a href="#platform-support">Platforms</a> ·
  <a href="#features">Features</a> ·
  <a href="#building-from-source">Build from source</a> ·
  <a href="CONTRIBUTING.md">Contribute</a>
</p>

![Wallcraft library](docs/screenshot.png)

## Features

**Library**
- Add folders (scanned recursively and watched for new files) or individual files, or drag and drop them onto the window.
- Search, filter by images / live / favourites, and preview with resolution and file size.
- Set a different wallpaper on each monitor, with every fit mode: fill, fit, stretch, center, tile and span.
- WebP and other formats your desktop can't show natively are converted automatically.

**Two layers: static and animated**
- Every monitor has a **static** wallpaper (your regular desktop wallpaper: JPG, PNG, WebP…) and an optional **animated** one (MP4, WebM, GIF…) playing on top.
- Setting an animated wallpaper never replaces your static one. Remove the animation, or let a battery rule stop it, and your static wallpaper is right there.
- The library has separate **Static** and **Animated** tabs, and every wallpaper is tagged with its file type.

**Live wallpapers**
- Videos and animated images play *behind your desktop icons*, on one or all monitors:
  - **Video:** MP4, M4V, MOV, MKV, WebM, AVI, WMV, ASF, MPG/MPEG, M2V, VOB, TS, M2TS, MTS, FLV, F4V, 3GP, 3G2, OGV
  - **Codecs:** H.264, H.265/HEVC, VP8, VP9, AV1\*, MPEG-1/2/4, WMV, Theora, Motion JPEG
  - **Animated images:** GIF and animated WebP (a still WebP is treated as a normal image)

  \*AV1 needs a graphics card with AV1 decoding (most from 2020 onward).
- Works like Lively Wallpaper: each live wallpaper plays with hardware video decoding, behind the desktop icons. On Windows it runs in its own [mpv](https://mpv.io) process and supports the Windows 11 24H2 desktop. See [Platform support](#platform-support) for Linux and macOS.
- If a player crashes, or Explorer restarts, Wallcraft restarts the player and puts it back in place.
- Muted by default. With several monitors, only one plays sound.

**Modes**
| Mode | What it does |
| --- | --- |
| Manual | You pick the wallpaper (per monitor if you like). |
| Slideshow | Rotates through your whole library or a custom playlist, in order or shuffled, every *N* minutes. |
| Time of day | Switches wallpaper at fixed times or at **dawn, sunrise, solar noon, sunset and dusk**, with offsets (for example "30 minutes before sunset"). Sun times are calculated offline from your location. |
| Follow system theme | Uses one wallpaper in light mode and another in dark mode, and swaps as soon as the system switches. |

**Theme sync**
- Automatically switch the system between light and dark mode at sunrise/sunset or at custom times (on Windows: for apps, the taskbar, or both).
- Only switches at the scheduled moments, so you can still change the theme by hand in between.
- Wallcraft's own window follows the system theme too (or pick light/dark).

**Performance and battery rules**

Live wallpapers can pause (freeze the frame) or stop (unload the video so your static wallpaper shows) when:
- the laptop is on battery, below a battery percentage you choose, or battery saver is on
- an app is fullscreen, such as a game, video or presentation (only on that monitor)
- a window is maximized (only on that monitor)
- the screen is locked

When several rules match, the strongest action wins. You can also pause from the tray at any time.

**Everyday comforts**
- **Refresh** (button, F5 or tray) re-applies every wallpaper if something looks wrong
- **Update checks**: a daily check (optional) and a *Check for updates* button. New versions show their release notes and download the right file for your install
- Tray icon with next/previous, pause and mode switching
- Start at login (no admin rights needed)
- Single instance: launching Wallcraft again just brings the window forward
- Portable mode, and recovers by itself if Explorer restarts or monitors change

## Platform support

| | Windows 10/11 | Linux | macOS 13+ *(experimental)* |
| --- | --- | --- | --- |
| Static wallpapers, slideshow, time of day | ✅ | ✅ GNOME, KDE Plasma, XFCE, Cinnamon, MATE, LXQt, sway, Hyprland; `feh` on other X11 window managers | ✅ (current Space only, a macOS limit) |
| Different wallpaper per monitor | ✅ | ✅ XFCE, sway, Hyprland. Other desktops use one wallpaper everywhere | ✅ |
| Animated wallpapers | ✅ | ✅ on X11 · ✅ Wayland with [mpvpaper](https://github.com/GhostNaN/mpvpaper) (sway, Hyprland, KDE) · ❌ GNOME on Wayland | ✅ |
| Switch light/dark mode | ✅ | ✅ GNOME, KDE, XFCE, Cinnamon, MATE | ✅ (asks permission once) |
| Battery, power-saver and lock rules | ✅ | ✅ | ✅ |
| Pause for fullscreen / maximized apps | ✅ | ✅ on X11 | ✅ |
| Start at login | ✅ | ✅ | ✅ |

**Linux notes**
- **GNOME on Wayland** doesn't let any app draw behind the desktop, so animated wallpapers need a GNOME on Xorg session there. Wallcraft explains this in the app.
- **XFCE, Cinnamon and MATE draw their desktop icons in a window of their own.** On those desktops an animated wallpaper may cover the icons. Static wallpapers and everything else work normally.
- For the smoothest video playback, install **mpv** (`sudo apt install mpv` or your distribution's equivalent). Without it, Wallcraft uses its built-in player.

**macOS notes:** macOS support is new and experimental, so please [report problems](../../issues/new/choose). macOS only lets apps change the wallpaper of the *current* Space; other Spaces keep theirs.

## Install

Download from the [latest release](../../releases/latest):

| System | File | Notes |
| --- | --- | --- |
| Windows | `Wallcraft-x.y.z-Setup.exe` | Normal install with a Start menu entry. Per user, no admin rights. |
| Windows | `Wallcraft-x.y.z-portable.exe` | A single exe, nothing to install. |
| Windows | `Wallcraft-x.y.z-win64.zip` | Unpacked folder (starts fastest). |
| Linux | `Wallcraft-x.y.z-x86_64.AppImage` | Runs on most distributions. Make it executable, then double-click it. |
| Linux | `Wallcraft-x.y.z-linux-x86_64.tar.gz` | Unpacked folder; run `Wallcraft/Wallcraft`. |
| macOS | `Wallcraft-x.y.z-macos-arm64.dmg` | Apple Silicon Macs (M1 and later). |
| macOS | `Wallcraft-x.y.z-macos-intel.dmg` | Intel Macs. |

`SHA256SUMS.txt` in each release lets you check your download.

### Windows
Requires Windows 10 (1809 or later) or Windows 11, 64-bit.

> **"Windows protected your PC"?** Release builds aren't code-signed yet, so SmartScreen may warn on first launch.
> Click **More info → Run anyway**.

### Linux
```bash
chmod +x Wallcraft-*-x86_64.AppImage
./Wallcraft-*-x86_64.AppImage
```
Some distributions need FUSE for AppImages (`sudo apt install libfuse2` on older Ubuntu). Otherwise use the `.tar.gz`.

### macOS
Open the `.dmg` and drag Wallcraft to **Applications**. The app isn't notarized by Apple yet, so the first time you open it:

1. Open Wallcraft and close the "Apple could not verify…" message.
2. Go to **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to Wallcraft.
3. Confirm with your password. After that it opens normally.

### Portable mode
Create a folder named `wallcraft-data` next to `Wallcraft.exe` (Windows) or next to the `.AppImage` (Linux). All settings, thumbnails and logs are then stored there instead of in your user profile.

## Using Wallcraft

1. **Library → Add folder…** and pick a folder of wallpapers.
2. Double-click a wallpaper to apply it, or select it and use the panel on the right to choose the monitor and fit.
3. To automate things, open **Slideshow**, **Time of day** or **Theme sync**, set it up, and click **Turn on**. Only one mode is active at a time. The current mode is also shown at the bottom of the sidebar and in the tray menu.
4. Adjust **Performance** rules if you use live wallpapers on a laptop.

Closing the window keeps Wallcraft running in the tray. Choose **Quit Wallcraft** from the tray menu to exit.

### Where settings are stored

| | Windows | Linux | macOS |
| --- | --- | --- | --- |
| Settings | `%APPDATA%\Wallcraft\config.json` | `~/.config/Wallcraft/config.json` | `~/Library/Application Support/Wallcraft/config.json` |
| Thumbnails and cache | `%LOCALAPPDATA%\Wallcraft\cache` | `~/.cache/Wallcraft/cache` | `~/Library/Caches/Wallcraft/cache` |
| Logs | `%LOCALAPPDATA%\Wallcraft\logs` | `~/.cache/Wallcraft/logs` | `~/Library/Caches/Wallcraft/logs` |

## Troubleshooting

- **The live wallpaper doesn't show, or vanished.** Press **F5** (Refresh) first. On Windows, Wallcraft re-attaches automatically after Explorer restarts. If it still isn't visible, open an issue with your system version and the log file attached. The log records which desktop layout was detected and every attach attempt.
- **Linux: "doesn't let apps draw behind the desktop".** You're on GNOME with Wayland; see the [Linux notes](#platform-support).
- **Linux: the app doesn't start from source with an "xcb" error.** Install `libxcb-cursor0` (`sudo apt install libxcb-cursor0`). The AppImage already includes it.
- **macOS: dark mode switching doesn't work.** Allow Wallcraft under **System Settings → Privacy & Security → Automation → System Events**.
- **The wallpaper looks blurry.** Turn on *Settings → Keep JPEG wallpapers at full quality* (Windows re-compresses JPEGs by default).
- **A video doesn't play.** Check the codec is in the list above. AV1 needs a graphics card that decodes it. The log file shows the decoder error.

## Building from source

You need Python 3.10+ (3.12 recommended) and Git.

```bash
git clone https://github.com/Noodz2Code/wallcraft.git
cd wallcraft
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate        # Linux and macOS
pip install -r requirements-dev.txt

python -m wallcraft              # run from source
python -m pytest                 # run the tests
```

On Linux, install the X11 cursor library Qt needs, plus mpv for video: `sudo apt install libxcb-cursor0 mpv` (Debian/Ubuntu/Mint).

### Building the downloads

| System | Commands | Output |
| --- | --- | --- |
| Windows | `powershell -ExecutionPolicy Bypass -File scripts\build.ps1` | `dist\Wallcraft.exe`, `dist\Wallcraft\` and, with [Inno Setup 6](https://jrsoftware.org/isdl.php), the installer. mpv is downloaded and bundled automatically. |
| Linux | `WALLCRAFT_ONEFILE=0 python -m PyInstaller --noconfirm wallcraft.spec` then `scripts/build_appimage.sh` | `dist/Wallcraft-x.y.z-x86_64.AppImage` and `.tar.gz` |
| macOS | `python -m PyInstaller --noconfirm wallcraft.spec` then `scripts/build_macos.sh` | `dist/Wallcraft.app` and `dist/Wallcraft-x.y.z-macos-<arch>.dmg` |

The release workflow builds all of them on GitHub when you push a version tag.

### Releasing

1. Update `__version__` in `src/wallcraft/__init__.py` and `CHANGELOG.md`.
2. Commit, then tag and push: `git tag v0.1.0 && git push origin v0.1.0`.
3. GitHub Actions tests and builds on Windows, Linux and macOS, then publishes one release with every download and the checksums. If an (experimental) macOS build fails, the release is published without it.

## How it works

```
src/wallcraft/
├── app.py               startup, logging, single instance, tray
├── controller.py        the engine: picks each monitor's static and animated wallpaper and keeps them applied
├── config.py            settings model and JSON persistence
├── schedule.py          time-of-day and theme scheduling
├── solar.py             offline sunrise/sunset calculation
├── slideshow.py         playlist ordering
├── rules.py             performance/battery rules
├── library.py           media types and folder scanning
├── updates.py           update check against GitHub releases
├── live/                animated wallpaper players (mpv processes, or the built-in Qt player)
├── services/            library, thumbnails, video still frames, config store, update checker
├── platform/            everything OS-specific, behind one Backend interface
│   ├── windows/         Win32 via ctypes: IDesktopWallpaper, WorkerW embedding, power, theme
│   ├── linux/           gsettings/xfconf/Plasma/sway adapters, X11 via libX11, sysfs + D-Bus
│   └── macos/           PyObjC: NSWorkspace, desktop-level windows, power, appearance
└── ui/                  Qt (PySide6) interface
```

- **Two layers.** Each monitor has a static wallpaper (set through the OS) and an optional animated one drawn on top by a player window. Changes to the static layer under a running animation wait until the animation stops.
- **Animated wallpapers on Windows** work like Lively Wallpaper. Each one runs in its own mpv process (`live/mpv.py`), controlled through mpv's JSON IPC. Wallcraft asks Explorer for a window layer (WorkerW) between the wallpaper and the icons and moves mpv's window into it (`platform/windows/desktop.py`), handling both the classic and the Windows 11 24H2 layout. A job object ends the players together with Wallcraft, even after a crash.
- **On Linux (X11)** Wallcraft opens its own window, marks it as a desktop window that sits below everything on every workspace, and mpv draws into it (`--wid`). **On Wayland**, `mpvpaper` draws the video on the compositor's background layer.
- **On macOS** a borderless window is raised to the desktop window level (below the Finder's icons) on every Space, and Qt plays the video with hardware decoding.
- Windows and Linux system calls use `ctypes`, so there are no compiled extensions. macOS uses PyObjC.

## Contributing

Bug reports, ideas and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Wallcraft is [MIT](LICENSE) licensed. Builds bundle third-party software under its own licenses, including mpv (GPL-2.0-or-later). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
