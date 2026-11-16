# Contributing to Wallcraft

Thanks for helping out! Bug reports, feature ideas, docs fixes and code are all welcome.

## Reporting bugs

Open an issue and include:
- your system: Windows version (`winver`); Linux distribution, desktop (GNOME, KDE, XFCE…) and X11 or Wayland;
  or macOS version. Plus the number and arrangement of monitors
- what you did, what you expected and what happened
- the log file (start Wallcraft with `--debug` for more detail): `%LOCALAPPDATA%\Wallcraft\logs\wallcraft.log`
  on Windows, `~/.cache/Wallcraft/logs/wallcraft.log` on Linux, `~/Library/Caches/Wallcraft/logs/wallcraft.log` on macOS

## Development setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m wallcraft --debug
```

Wallcraft runs on Windows, Linux and macOS, so you can work on the UI and engine on any of them.
Code that touches the desktop itself (`src/wallcraft/platform/<os>/`) has to be tested on that system.
macOS support is experimental: testers with a Mac are especially welcome.

## Before opening a pull request

```powershell
ruff check src tests
python -m pytest
```

- Keep pull requests focused on one change.
- Add or update tests for logic changes. Scheduling, rules, config and slideshow code are plain Python and easy to test.
- Platform-specific code belongs in `platform/`. The rest of the app talks to the `Backend` interface.
- If you change UI text, keep it short and in sentence case.
- Delayed calls must pass a context object: `QTimer.singleShot(ms, self, self.method)`, not
  `QTimer.singleShot(ms, self.method)`. Qt then cancels the timer if the object is destroyed first;
  without it, the callback runs on a deleted object and crashes.

## Code layout

See [How it works](README.md#how-it-works) in the README.
