# Contributing to Wallcraft

Thanks for helping out! Bug reports, feature ideas, docs fixes and code are all welcome.

## Reporting bugs

Open an issue and include:
- your Windows version (run `winver`) and number/arrangement of monitors
- what you did, what you expected and what happened
- the log file: `%LOCALAPPDATA%\Wallcraft\logs\wallcraft.log` (start Wallcraft with `--debug` for more detail)

## Development setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m wallcraft --debug
```

The app also runs on Linux/macOS using a development backend, which is handy for UI work.
Anything touching the desktop itself (`src/wallcraft/platform/windows/`) has to be tested on Windows.

## Before opening a pull request

```powershell
ruff check src tests
python -m pytest
```

- Keep pull requests focused on one change.
- Add or update tests for logic changes. Scheduling, rules, config and slideshow code are plain Python and easy to test.
- Platform-specific code belongs in `platform/`. The rest of the app talks to the `Backend` interface.
- If you change UI text, keep it short and in sentence case.

## Code layout

See [How it works](README.md#how-it-works) in the README.
