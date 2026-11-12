import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture
def wallcraft_home(tmp_path, monkeypatch):
    monkeypatch.setenv("WALLCRAFT_HOME", str(tmp_path / "home"))
    from wallcraft import paths

    paths.ensure_dirs()
    return tmp_path / "home"


def pump(ms: int) -> None:
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_until(predicate, timeout_ms: int = 5000) -> bool:
    waited = 0
    while waited < timeout_ms:
        if predicate():
            return True
        pump(50)
        waited += 50
    return predicate()
