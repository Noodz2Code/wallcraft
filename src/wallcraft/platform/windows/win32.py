"""ctypes bindings for the Win32 APIs Wallcraft uses. Imported only on Windows."""

# ruff: noqa: N801, N816 - keep Win32 naming
from __future__ import annotations

import ctypes
import uuid
from ctypes import wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32")
ole32 = ctypes.WinDLL("ole32")
dwmapi = ctypes.WinDLL("dwmapi")

LRESULT = ctypes.c_ssize_t
LONG_PTR = ctypes.c_ssize_t
HRESULT_T = ctypes.c_long  # checked manually, never raises

# Messages / flags --------------------------------------------------------- #
WM_SETTINGCHANGE = 0x001A
HWND_BROADCAST = 0xFFFF
SMTO_NORMAL = 0x0000
SMTO_ABORTIFHUNG = 0x0002
WM_SPAWN_WORKER = 0x052C

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000
WS_EX_LAYERED = 0x00080000
LWA_ALPHA = 0x2

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SW_SHOWNA = 8
GA_PARENT = 1

RDW_INVALIDATE = 0x0001
RDW_ERASE = 0x0004
RDW_ALLCHILDREN = 0x0080
RDW_UPDATENOW = 0x0100

MONITOR_DEFAULTTONULL = 0
MONITORINFOF_PRIMARY = 1

SPI_GETDESKWALLPAPER = 0x0073
SPI_SETDESKWALLPAPER = 0x0014
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

DESKTOP_SWITCHDESKTOP = 0x0100
DWMWA_CLOAKED = 14

# SHQueryUserNotificationState results
QUNS_BUSY = 2
QUNS_RUNNING_D3D_FULL_SCREEN = 3
QUNS_PRESENTATION_MODE = 4

COINIT_APARTMENTTHREADED = 0x2
CLSCTX_ALL = 0x17


# Structures --------------------------------------------------------------- #
class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("rcMonitor", wt.RECT),
        ("rcWork", wt.RECT),
        ("dwFlags", wt.DWORD),
        ("szDevice", wt.WCHAR * 32),
    ]


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", wt.DWORD),
        ("BatteryFullLifeTime", wt.DWORD),
    ]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, value: str) -> GUID:
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
MONITORENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)


def _fn(dll, name, restype, *argtypes):
    f = getattr(dll, name)
    f.restype = restype
    f.argtypes = argtypes
    return f


# user32
FindWindowW = _fn(user32, "FindWindowW", wt.HWND, wt.LPCWSTR, wt.LPCWSTR)
FindWindowExW = _fn(user32, "FindWindowExW", wt.HWND, wt.HWND, wt.HWND, wt.LPCWSTR, wt.LPCWSTR)
SendMessageTimeoutW = _fn(
    user32, "SendMessageTimeoutW", LRESULT,
    wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_size_t),
)
EnumWindows = _fn(user32, "EnumWindows", wt.BOOL, WNDENUMPROC, wt.LPARAM)
SetParent = _fn(user32, "SetParent", wt.HWND, wt.HWND, wt.HWND)
GetAncestor = _fn(user32, "GetAncestor", wt.HWND, wt.HWND, wt.UINT)
IsWindow = _fn(user32, "IsWindow", wt.BOOL, wt.HWND)
IsWindowVisible = _fn(user32, "IsWindowVisible", wt.BOOL, wt.HWND)
IsIconic = _fn(user32, "IsIconic", wt.BOOL, wt.HWND)
IsZoomed = _fn(user32, "IsZoomed", wt.BOOL, wt.HWND)
GetWindowRect = _fn(user32, "GetWindowRect", wt.BOOL, wt.HWND, ctypes.POINTER(wt.RECT))
MapWindowPoints = _fn(user32, "MapWindowPoints", ctypes.c_int, wt.HWND, wt.HWND, ctypes.POINTER(wt.POINT), wt.UINT)
SetWindowPos = _fn(
    user32, "SetWindowPos", wt.BOOL,
    wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT,
)
ShowWindow = _fn(user32, "ShowWindow", wt.BOOL, wt.HWND, ctypes.c_int)
GetClassNameW = _fn(user32, "GetClassNameW", ctypes.c_int, wt.HWND, wt.LPWSTR, ctypes.c_int)
GetWindowThreadProcessId = _fn(user32, "GetWindowThreadProcessId", wt.DWORD, wt.HWND, ctypes.POINTER(wt.DWORD))
GetForegroundWindow = _fn(user32, "GetForegroundWindow", wt.HWND)
MonitorFromWindow = _fn(user32, "MonitorFromWindow", wt.HMONITOR, wt.HWND, wt.DWORD)
GetMonitorInfoW = _fn(user32, "GetMonitorInfoW", wt.BOOL, wt.HMONITOR, ctypes.POINTER(MONITORINFOEXW))
EnumDisplayMonitors = _fn(
    user32, "EnumDisplayMonitors", wt.BOOL, wt.HDC, ctypes.POINTER(wt.RECT), MONITORENUMPROC, wt.LPARAM
)
SetLayeredWindowAttributes = _fn(
    user32, "SetLayeredWindowAttributes", wt.BOOL, wt.HWND, wt.DWORD, ctypes.c_ubyte, wt.DWORD
)
SystemParametersInfoW = _fn(user32, "SystemParametersInfoW", wt.BOOL, wt.UINT, wt.UINT, ctypes.c_void_p, wt.UINT)
RedrawWindow = _fn(user32, "RedrawWindow", wt.BOOL, wt.HWND, ctypes.POINTER(wt.RECT), wt.HANDLE, wt.UINT)
OpenInputDesktop = _fn(user32, "OpenInputDesktop", wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
SwitchDesktop = _fn(user32, "SwitchDesktop", wt.BOOL, wt.HANDLE)
CloseDesktop = _fn(user32, "CloseDesktop", wt.BOOL, wt.HANDLE)

if ctypes.sizeof(ctypes.c_void_p) == 8:
    GetWindowLongPtrW = _fn(user32, "GetWindowLongPtrW", LONG_PTR, wt.HWND, ctypes.c_int)
    SetWindowLongPtrW = _fn(user32, "SetWindowLongPtrW", LONG_PTR, wt.HWND, ctypes.c_int, LONG_PTR)
else:  # 32-bit Windows exports only the non-Ptr variants
    GetWindowLongPtrW = _fn(user32, "GetWindowLongW", LONG_PTR, wt.HWND, ctypes.c_int)
    SetWindowLongPtrW = _fn(user32, "SetWindowLongW", LONG_PTR, wt.HWND, ctypes.c_int, LONG_PTR)

# kernel32
GetSystemPowerStatus = _fn(kernel32, "GetSystemPowerStatus", wt.BOOL, ctypes.POINTER(SYSTEM_POWER_STATUS))
GetCurrentProcessId = _fn(kernel32, "GetCurrentProcessId", wt.DWORD)

# shell32
SHQueryUserNotificationState = _fn(shell32, "SHQueryUserNotificationState", HRESULT_T, ctypes.POINTER(ctypes.c_int))
SetCurrentProcessExplicitAppUserModelID = _fn(
    shell32, "SetCurrentProcessExplicitAppUserModelID", HRESULT_T, wt.LPCWSTR
)

# dwmapi
DwmGetWindowAttribute = _fn(dwmapi, "DwmGetWindowAttribute", HRESULT_T, wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD)

# ole32
CoInitializeEx = _fn(ole32, "CoInitializeEx", HRESULT_T, ctypes.c_void_p, wt.DWORD)
CoCreateInstance = _fn(
    ole32, "CoCreateInstance", HRESULT_T,
    ctypes.POINTER(GUID), ctypes.c_void_p, wt.DWORD, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
)
CoTaskMemFree = _fn(ole32, "CoTaskMemFree", None, ctypes.c_void_p)


# Helpers ------------------------------------------------------------------ #
def class_name(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    r = wt.RECT()
    if not GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def window_pid(hwnd: int) -> int:
    pid = wt.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def is_cloaked(hwnd: int) -> bool:
    cloaked = wt.DWORD()
    hr = DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return hr >= 0 and cloaked.value != 0


def monitor_info(hmon) -> MONITORINFOEXW | None:
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    if not GetMonitorInfoW(hmon, ctypes.byref(info)):
        return None
    return info


def enum_windows() -> list[int]:
    handles: list[int] = []

    @WNDENUMPROC
    def _cb(hwnd, _lparam):
        handles.append(hwnd)
        return True

    EnumWindows(_cb, 0)
    return handles


def enum_monitors() -> list[tuple[str, tuple[int, int, int, int], bool]]:
    """(device name, physical rect, is_primary) for each active display."""
    result: list[tuple[str, tuple[int, int, int, int], bool]] = []

    @MONITORENUMPROC
    def _cb(hmon, _hdc, _rect, _lparam):
        info = monitor_info(hmon)
        if info is not None:
            r = info.rcMonitor
            result.append((info.szDevice, (r.left, r.top, r.right - r.left, r.bottom - r.top),
                           bool(info.dwFlags & MONITORINFOF_PRIMARY)))
        return True

    EnumDisplayMonitors(None, None, _cb, 0)
    return result


def co_initialize() -> None:
    # S_FALSE / RPC_E_CHANGED_MODE just mean COM is already initialised on this thread.
    CoInitializeEx(None, COINIT_APARTMENTTHREADED)


def broadcast_setting_change(area: str, timeout_ms: int = 200) -> None:
    buf = ctypes.create_unicode_buffer(area)
    result = ctypes.c_size_t()
    SendMessageTimeoutW(
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, ctypes.cast(buf, ctypes.c_void_p).value,
        SMTO_ABORTIFHUNG, timeout_ms, ctypes.byref(result),
    )
