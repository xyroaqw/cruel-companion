"""Makes a Tk window click-through (mouse events pass to whatever is behind it) via the
WS_EX_TRANSPARENT extended window style. Safe to apply unconditionally here since the HUD has
no buttons or interactive elements -- there is nothing in it the user ever needs to click.
"""

import ctypes
import sys
import warnings
from ctypes import wintypes

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
GA_ROOT = 2


def make_window_clickthrough(hwnd: int) -> None:
    if sys.platform != "win32":
        warnings.warn("make_window_clickthrough is a no-op outside Windows", RuntimeWarning)
        return

    user32 = ctypes.windll.user32
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongW.restype = wintypes.LONG
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]

    # Tk's winfo_id() is the INNER child window, not the real top-level. Making the child
    # layered breaks the top-level's -transparentcolor colorkey (HUD renders as an opaque
    # box), so always apply the styles to the top-level ancestor.
    top = user32.GetAncestor(hwnd, GA_ROOT) or hwnd
    current_style = user32.GetWindowLongW(top, GWL_EXSTYLE)
    user32.SetWindowLongW(top, GWL_EXSTYLE, current_style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
