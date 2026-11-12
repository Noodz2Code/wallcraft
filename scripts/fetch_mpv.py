"""Download the Windows build of mpv that Wallcraft bundles, into vendor/mpv/.

mpv plays live wallpapers in its own process, the same way Lively Wallpaper uses it.
Builds come from https://github.com/shinchiro/mpv-winbuild-cmake, which publishes a
release daily and keeps about 30 days of them, so by default the latest release is used.
The archive's SHA-256 is checked against the digest GitHub publishes for the asset.

The archive needs 7-Zip to extract (it uses the BCJ2 filter). The script uses 7z/7zz/7za
from PATH or Program Files; on Windows it otherwise downloads the official standalone
7zr.exe from 7-zip.org.

Usage:
    python scripts/fetch_mpv.py              # latest build, skipped if already present
    python scripts/fetch_mpv.py --force      # re-download
    python scripts/fetch_mpv.py --tag 20261111
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import date
from pathlib import Path

REPO = "shinchiro/mpv-winbuild-cmake"
# Baseline x86-64 build. The "-v3-" variant needs AVX2 CPUs, so it isn't used.
ASSET = re.compile(r"^mpv-x86_64-\d{8}-git-([0-9a-f]+)\.7z$")
SEVEN_ZR_URL = "https://www.7-zip.org/a/7zr.exe"
ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "vendor" / "mpv"
HEADERS = {"User-Agent": "wallcraft-build-script", "Accept": "application/vnd.github+json"}


def http_get(url: str, headers: dict | None = None) -> urllib.request.addinfourl:
    h = dict(HEADERS, **(headers or {}))
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        h["Authorization"] = f"Bearer {token}"
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120)


def release(tag: str | None) -> dict:
    url = f"https://api.github.com/repos/{REPO}/releases/" + (f"tags/{tag}" if tag else "latest")
    with http_get(url) as resp:
        return json.load(resp)


def download(url: str, target: Path) -> str:
    sha = hashlib.sha256()
    with http_get(url, {"Accept": "application/octet-stream"}) as resp, open(target, "wb") as fh:
        while chunk := resp.read(1 << 20):
            sha.update(chunk)
            fh.write(chunk)
    return sha.hexdigest()


def find_7z(workdir: Path) -> str:
    for name in ("7z", "7zz", "7za"):
        exe = shutil.which(name)
        if exe:
            return exe
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
        if base and (Path(base) / "7-Zip" / "7z.exe").is_file():
            return str(Path(base) / "7-Zip" / "7z.exe")
    if sys.platform == "win32":
        exe = workdir / "7zr.exe"
        print(f"7-Zip not found; downloading {SEVEN_ZR_URL}")
        download(SEVEN_ZR_URL, exe)
        return str(exe)
    sys.exit("7-Zip is required to extract mpv (install p7zip / 7zip).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", help="release tag (YYYYMMDD); default: latest")
    parser.add_argument("--force", action="store_true", help="download even if already present")
    args = parser.parse_args()

    rel = release(args.tag)
    asset = next((a for a in rel["assets"] if ASSET.match(a["name"])), None)
    if asset is None:
        sys.exit(f"No x86_64 mpv archive in release {rel.get('tag_name')}")
    version_file = DEST / "VERSION.txt"
    if (not args.force and (DEST / "mpv.exe").is_file() and version_file.is_file()
            and asset["name"] in version_file.read_text(encoding="utf-8")):
        print(f"mpv already up to date ({asset['name']})")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        archive = tmpdir / asset["name"]
        print(f"Downloading {asset['name']} ({asset['size'] // 1_000_000} MB)")
        actual = download(asset["browser_download_url"], archive)
        expected = (asset.get("digest") or "").removeprefix("sha256:")
        if expected and actual != expected:
            sys.exit(f"Checksum mismatch for {asset['name']}: expected {expected}, got {actual}")
        print(f"SHA-256 {actual} " + ("(verified against GitHub)" if expected else "(no published digest)"))

        out = tmpdir / "out"
        subprocess.run([find_7z(tmpdir), "x", "-y", f"-o{out}", str(archive), "mpv.exe"],
                       check=True, stdout=subprocess.DEVNULL)
        if DEST.exists():
            shutil.rmtree(DEST)
        DEST.mkdir(parents=True)
        shutil.copy2(out / "mpv.exe", DEST / "mpv.exe")

    commit = ASSET.match(asset["name"]).group(1)
    version_file.write_text(
        f"mpv for Windows, bundled with Wallcraft\n"
        f"Archive:   {asset['name']}\n"
        f"SHA-256:   {actual}\n"
        f"Release:   https://github.com/{REPO}/releases/tag/{rel['tag_name']}\n"
        f"mpv source (commit {commit}): https://github.com/mpv-player/mpv/tree/{commit}\n"
        f"Build scripts: https://github.com/{REPO}\n"
        f"Fetched:   {date.today().isoformat()}\n",
        encoding="utf-8",
    )
    (DEST / "LICENSE.txt").write_text(
        "mpv is free software licensed under the GNU General Public License, version 2 or later\n"
        "(this build includes GPL components). Wallcraft runs it as a separate program.\n\n"
        "Full license text: https://github.com/mpv-player/mpv/blob/master/Copyright\n"
        "Source code for this exact build: see VERSION.txt for the mpv commit and build scripts.\n",
        encoding="utf-8",
    )
    print(f"mpv ready in {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
