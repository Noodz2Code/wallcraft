"""Tie player processes to Wallcraft's lifetime with a Windows job object.

If Wallcraft exits or crashes, Windows closes the job handle and terminates every
mpv process in it, so no orphaned video keeps playing behind the desktop.
"""

from __future__ import annotations

import ctypes
import logging

from . import win32

log = logging.getLogger(__name__)


class KillOnCloseJob:
    def __init__(self) -> None:
        self._handle = win32.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = win32.JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = win32.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not win32.SetInformationJobObject(self._handle, win32.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                                             ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, pid: int) -> bool:
        proc = win32.OpenProcess(win32.PROCESS_SET_QUOTA | win32.PROCESS_TERMINATE, False, pid)
        if not proc:
            log.warning("OpenProcess(%s) failed: %s", pid, ctypes.get_last_error())
            return False
        try:
            if not win32.AssignProcessToJobObject(self._handle, proc):
                log.warning("AssignProcessToJobObject(%s) failed: %s", pid, ctypes.get_last_error())
                return False
            return True
        finally:
            win32.CloseHandle(proc)
