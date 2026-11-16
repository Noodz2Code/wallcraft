"""Checking GitHub for a newer Wallcraft release (no Qt dependency).

Only the public "latest release" endpoint is queried, with a generic user agent;
nothing about the user or their system is sent.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import REPO_URL, __version__

TIMEOUT_S = 15


def api_url(repo_url: str = REPO_URL) -> str:
    owner_repo = repo_url.rstrip("/").split("github.com/", 1)[1]
    return f"https://api.github.com/repos/{owner_repo}/releases/latest"


def parse_version(text: str) -> tuple[int, ...]:
    """'v0.1.5' -> (0, 1, 5). Pre-release suffixes ('-beta', '.dev1') are ignored."""
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)", text or "")
    if not m:
        return ()
    nums = [int(n) for n in m.group(1).split(".")]
    while len(nums) > 1 and nums[-1] == 0:
        nums.pop()  # 0.2 == 0.2.0
    return tuple(nums)


def is_newer(latest: str, current: str = __version__) -> bool:
    lv, cv = parse_version(latest), parse_version(current)
    return bool(lv) and lv > cv


def install_kind() -> str:
    """How this copy was installed: "installer", "portable" (single exe), "zip" or "source"."""
    if not getattr(sys, "frozen", False):
        return "source"
    exe_dir = Path(sys.executable).resolve().parent
    meipass = Path(getattr(sys, "_MEIPASS", exe_dir)).resolve()
    if meipass != exe_dir and not str(meipass).startswith(str(exe_dir)):
        return "portable"  # one-file build unpacks to a temp folder
    programs = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"
    if os.environ.get("LOCALAPPDATA") and str(exe_dir).lower().startswith(str(programs).lower()):
        return "installer"
    return "zip"


@dataclass(frozen=True)
class Release:
    version: str        # "0.1.5"
    tag: str            # "v0.1.5"
    page_url: str       # release page on GitHub
    notes: str          # release notes (Markdown)
    published: str      # ISO date
    assets: dict[str, str]  # file name -> download URL

    def download_url(self, kind: str) -> str:
        """Best download for this install type, falling back to the release page."""
        suffix = {"installer": "-Setup.exe", "portable": "-portable.exe", "zip": "-win64.zip"}.get(kind)
        if suffix:
            for name, url in self.assets.items():
                if name.endswith(suffix):
                    return url
        return self.page_url


def parse_release(data: dict) -> Release:
    tag = str(data.get("tag_name") or "")
    return Release(
        version=".".join(str(n) for n in parse_version(tag)) or tag,
        tag=tag,
        page_url=str(data.get("html_url") or f"{REPO_URL}/releases"),
        notes=str(data.get("body") or ""),
        published=str(data.get("published_at") or "")[:10],
        assets={a["name"]: a["browser_download_url"] for a in data.get("assets", [])
                if a.get("name") and a.get("browser_download_url")},
    )


class UpdateError(Exception):
    pass


def fetch_latest(url: str | None = None, timeout: float = TIMEOUT_S) -> Release:
    req = urllib.request.Request(url or api_url(), headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"Wallcraft/{__version__}",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("No releases have been published yet.") from exc
        if exc.code == 403:
            raise UpdateError("GitHub is rate-limiting requests. Try again in a little while.") from exc
        raise UpdateError(f"GitHub returned an error ({exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError("Couldn't reach GitHub. Check your internet connection.") from exc
    except ValueError as exc:
        raise UpdateError("GitHub sent a response Wallcraft couldn't read.") from exc
    if not isinstance(data, dict) or not data.get("tag_name"):
        raise UpdateError("GitHub sent a response Wallcraft couldn't read.")
    return parse_release(data)
