"""Update checks: version logic, GitHub response parsing, and the Qt checker against a local fake API."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from conftest import wait_until
from wallcraft import updates
from wallcraft.updates import UpdateError, api_url, fetch_latest, is_newer, parse_release, parse_version

RELEASE = {
    "tag_name": "v9.9.0",
    "html_url": "https://github.com/example/wallcraft/releases/tag/v9.9.0",
    "body": "## What's new\n- Things",
    "published_at": "2026-11-20T10:00:00Z",
    "assets": [
        {"name": "Wallcraft-9.9.0-Setup.exe", "browser_download_url": "https://dl/setup.exe"},
        {"name": "Wallcraft-9.9.0-portable.exe", "browser_download_url": "https://dl/portable.exe"},
        {"name": "Wallcraft-9.9.0-win64.zip", "browser_download_url": "https://dl/win64.zip"},
        {"name": "Wallcraft-9.9.0-x86_64.AppImage", "browser_download_url": "https://dl/app.AppImage"},
        {"name": "Wallcraft-9.9.0-linux-x86_64.tar.gz", "browser_download_url": "https://dl/linux.tar.gz"},
        {"name": "Wallcraft-9.9.0-macos-arm64.dmg", "browser_download_url": "https://dl/arm.dmg"},
        {"name": "Wallcraft-9.9.0-macos-intel.dmg", "browser_download_url": "https://dl/intel.dmg"},
        {"name": "SHA256SUMS.txt", "browser_download_url": "https://dl/sums.txt"},
    ],
}


def test_parse_version():
    assert parse_version("v0.1.5") == (0, 1, 5)
    assert parse_version("0.2") == parse_version("0.2.0") == (0, 2)
    assert parse_version("v1.0.0-beta.2") == (1,)
    assert parse_version("nonsense") == ()


def test_is_newer():
    assert is_newer("v0.1.10", "0.1.9")  # numeric, not alphabetical
    assert is_newer("0.2.0", "0.1.99")
    assert not is_newer("v0.1.5", "0.1.5")
    assert not is_newer("0.1.4", "0.1.5")
    assert not is_newer("garbage", "0.1.5")


def test_api_url():
    assert api_url("https://github.com/Owner/repo") == "https://api.github.com/repos/Owner/repo/releases/latest"


def test_parse_release_and_download_choice():
    rel = parse_release(RELEASE)
    assert rel.version == "9.9" and rel.tag == "v9.9.0" and rel.published == "2026-11-20"
    assert rel.download_url("installer") == "https://dl/setup.exe"
    assert rel.download_url("portable") == "https://dl/portable.exe"
    assert rel.download_url("zip") == "https://dl/win64.zip"
    assert rel.download_url("appimage") == "https://dl/app.AppImage"
    assert rel.download_url("linux-tar") == "https://dl/linux.tar.gz"
    assert rel.download_url("macos-arm64") == "https://dl/arm.dmg"
    assert rel.download_url("macos-intel") == "https://dl/intel.dmg"
    assert rel.download_url("source") == rel.page_url
    bare = parse_release({"tag_name": "v1.0.0", "html_url": "https://page"})
    assert bare.download_url("installer") == "https://page"  # no assets: fall back to the page


def test_running_from_source_is_detected():
    assert updates.install_kind() == "source"


class FakeGitHub:
    """Tiny HTTP server answering like GitHub's releases/latest endpoint."""

    def __init__(self):
        self.status = 200
        self.payload: object = RELEASE
        self.user_agents: list[str] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                fake.user_agents.append(self.headers.get("User-Agent", ""))
                body = (self.payload_bytes())
                self.send_response(fake.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def payload_bytes(self):
                p = fake.payload
                return p if isinstance(p, bytes) else json.dumps(p).encode()

            def log_message(self, *_args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/releases/latest"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def github():
    fake = FakeGitHub()
    yield fake
    fake.close()


def test_fetch_latest(github):
    rel = fetch_latest(github.url)
    assert rel.version == "9.9"
    assert github.user_agents[-1].startswith("Wallcraft/")  # generic agent, nothing personal


def test_fetch_errors_are_friendly(github):
    github.status = 404
    with pytest.raises(UpdateError, match="No releases"):
        fetch_latest(github.url)
    github.status, github.payload = 200, b"<html>not json"
    with pytest.raises(UpdateError, match="couldn't read"):
        fetch_latest(github.url)
    github.close()
    with pytest.raises(UpdateError, match="Couldn't reach GitHub"):
        fetch_latest(github.url, timeout=2)


@pytest.fixture
def checker(qapp, wallcraft_home, github):
    from wallcraft import paths
    from wallcraft.services.config_store import ConfigStore
    from wallcraft.services.updater import UpdateChecker

    store = ConfigStore(paths.config_file())
    c = UpdateChecker(store, url=github.url)
    events = []
    c.available.connect(lambda r, manual: events.append(("available", r.version, manual)))
    c.up_to_date.connect(lambda r, manual: events.append(("up_to_date", r.version, manual)))
    c.failed.connect(lambda msg, manual: events.append(("failed", msg, manual)))
    c.finished.connect(lambda: events.append(("finished",)))
    return c, store, events


def run(c, events, manual=True):
    events.clear()
    c.check(manual=manual)
    assert wait_until(lambda: ("finished",) in events, 8000)
    return [e for e in events if e != ("finished",)]


def test_checker_reports_newer_release(checker):
    c, store, events = checker
    assert run(c, events) == [("available", "9.9", True)]
    assert c.update_available and store.config.state.last_update_check > 0


def test_skipped_version_is_quiet_automatically_but_not_manually(checker):
    c, _store, events = checker
    c.skip(parse_release(RELEASE))
    assert run(c, events, manual=False) == []
    assert run(c, events, manual=True) == [("available", "9.9", True)]


def test_checker_up_to_date(checker, github):
    from wallcraft import __version__

    c, _store, events = checker
    github.payload = dict(RELEASE, tag_name=f"v{__version__}")
    assert run(c, events) == [("up_to_date", ".".join(map(str, parse_version(__version__))), True)]
    assert not c.update_available


def test_checker_failure(checker, github):
    c, _store, events = checker
    github.status = 404
    result = run(c, events)
    assert result[0][0] == "failed" and "No releases" in result[0][1]
    assert c.last_error


def test_automatic_check_respects_setting_and_interval(checker):
    import time

    c, store, events = checker
    store.config.general.check_updates = False
    c._auto_check()
    assert not c.busy
    store.config.general.check_updates = True
    store.config.state.last_update_check = time.time()  # checked just now
    c._auto_check()
    assert not c.busy
    store.config.state.last_update_check = 0
    c._auto_check()
    assert c.busy
    assert wait_until(lambda: ("finished",) in events, 8000)
