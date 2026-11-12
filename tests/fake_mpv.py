#!/usr/bin/env python3
"""Stand-in for mpv in tests: speaks mpv's JSON IPC over a Unix socket and records commands.

Environment:
    FAKE_MPV_LOG       file that receives one JSON line per event (argv, commands)
    FAKE_MPV_EXIT_AFTER  seconds after which the process exits with code 3 (simulated crash)
"""

import json
import os
import socket
import sys
import threading
import time

OPTIONS = ["osc", "media-controls", "auto-window-resize", "keepaspect-window", "input-vo-keyboard"]


def record(event: dict) -> None:
    path = os.environ.get("FAKE_MPV_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")


def main() -> int:
    if "--list-options" in sys.argv:
        for name in OPTIONS:
            print(f" --{name:<30} Flag")
        return 0
    record({"argv": sys.argv[1:]})
    ipc = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--input-ipc-server="))
    crash_after = float(os.environ.get("FAKE_MPV_EXIT_AFTER", "0") or 0)
    if crash_after:
        threading.Timer(crash_after, lambda: os._exit(3)).start()

    if os.path.exists(ipc):
        os.unlink(ipc)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(ipc)
    server.listen(4)
    deadline = time.time() + 30
    while time.time() < deadline:
        server.settimeout(1.0)
        try:
            conn, _ = server.accept()
        except TimeoutError:
            continue
        buf = b""
        conn.settimeout(1.0)
        while time.time() < deadline:
            try:
                chunk = conn.recv(4096)
            except TimeoutError:
                continue
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                cmd = json.loads(line)["command"]
                record({"command": cmd})
                conn.sendall(b'{"error":"success","request_id":0}\n')
                if cmd == ["quit"]:
                    os.unlink(ipc)
                    return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
