"""Locates the AQW game window (Artix Games Launcher) by title substring and returns its
client area in screen coordinates, so capture excludes the title bar and borders. Pure
ctypes, matching ui/clickthrough_win32.py -- no pywin32 dependency.
"""

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowRect:
    left: int
    top: int
    width: int
    height: int


def ensure_dpi_aware() -> None:
    """Windows lies to non-DPI-aware processes about coordinates on scaled displays
    (125%/150%), which would misalign the capture region against mss's physical pixels.
    Call once at process start, before any Tk window is created."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def find_game_window(title_substrings: list[str]) -> WindowRect | None:
    """Returns the client rect of the first visible, non-minimized top-level window whose
    title contains any of the given substrings (case-insensitive), or None."""
    if sys.platform != "win32":
        return None

    user32 = ctypes.windll.user32
    needles = [s.lower() for s in title_substrings if s]
    matches: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum_cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.lower()
        if any(needle in title for needle in needles):
            matches.append(hwnd)
            return False  # stop enumeration at the first match
        return True

    user32.EnumWindows(_enum_cb, 0)
    if not matches:
        return None
    return _client_rect_on_screen(user32, matches[0])


def _client_rect_on_screen(user32, hwnd: int) -> WindowRect | None:
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return None
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None

    origin = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    return WindowRect(left=origin.x, top=origin.y, width=width, height=height)
