"""Ensure only one Wallcraft runs per user; a second launch focuses the first."""

from __future__ import annotations

import getpass
import re

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, app_id: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        try:
            user = getpass.getuser()
        except Exception:  # noqa: BLE001
            user = "user"
        self._key = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{app_id}-{user}")
        self._server: QLocalServer | None = None

    def acquire(self) -> bool:
        """True if this is the first instance. Otherwise asks the running one to show itself."""
        sock = QLocalSocket()
        sock.connectToServer(self._key)
        if sock.waitForConnected(400):
            sock.write(b"show\n")
            sock.flush()
            sock.waitForBytesWritten(400)
            sock.disconnectFromServer()
            return False
        # Nobody answered: clean up a stale socket from a crash and take over.
        QLocalServer.removeServer(self._key)
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not self._server.listen(self._key):
            return True  # can't listen, but don't block startup over it
        self._server.newConnection.connect(self._on_connection)
        return True

    def _on_connection(self) -> None:
        while self._server and self._server.hasPendingConnections():
            conn = self._server.nextPendingConnection()
            conn.readyRead.connect(conn.readAll)
            conn.disconnected.connect(conn.deleteLater)
            self.activated.emit()
