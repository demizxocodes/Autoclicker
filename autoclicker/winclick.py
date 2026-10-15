"""Background clicking on Windows: post mouse messages to a window, never touch the cursor.

A point remembers which top-level window it belongs to (title + class) and where
inside that window's client area it is, so it keeps working if the window moves
or sits behind other windows. It does not work while the window is minimized.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _sig(name, restype, *argtypes):
        fn = getattr(user32, name)
        fn.restype = restype
        fn.argtypes = argtypes
        return fn

    WindowFromPoint = _sig("WindowFromPoint", wintypes.HWND, wintypes.POINT)
    GetAncestor = _sig("GetAncestor", wintypes.HWND, wintypes.HWND, wintypes.UINT)
    ChildWindowFromPointEx = _sig(
        "ChildWindowFromPointEx", wintypes.HWND, wintypes.HWND, wintypes.POINT, wintypes.UINT
    )
    ClientToScreen = _sig("ClientToScreen", wintypes.BOOL, wintypes.HWND, ctypes.POINTER(wintypes.POINT))
    ScreenToClient = _sig("ScreenToClient", wintypes.BOOL, wintypes.HWND, ctypes.POINTER(wintypes.POINT))
    GetWindowTextW = _sig("GetWindowTextW", ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    GetClassNameW = _sig("GetClassNameW", ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    EnumWindows = _sig("EnumWindows", wintypes.BOOL, WNDENUMPROC, wintypes.LPARAM)
    IsWindowVisible = _sig("IsWindowVisible", wintypes.BOOL, wintypes.HWND)
    IsIconic = _sig("IsIconic", wintypes.BOOL, wintypes.HWND)
    PostMessageW = _sig("PostMessageW", wintypes.BOOL, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

GA_ROOT = 2
CWP_SKIPINVISIBLE, CWP_SKIPDISABLED, CWP_SKIPTRANSPARENT = 1, 2, 4
WM_MOUSEMOVE = 0x0200
# button -> (down, up, double-click, key-state flag)
MESSAGES = {
    "left": (0x0201, 0x0202, 0x0203, 0x0001),
    "right": (0x0204, 0x0205, 0x0206, 0x0002),
    "middle": (0x0207, 0x0208, 0x0209, 0x0010),
}

SUPPORTED = sys.platform == "win32"


@dataclass
class WindowSpot:
    title: str
    class_name: str
    rel_x: int  # position inside the window's client area
    rel_y: int


def _text(fn, hwnd) -> str:
    buf = ctypes.create_unicode_buffer(512)
    fn(hwnd, buf, len(buf))
    return buf.value


def window_at(x: int, y: int) -> WindowSpot | None:
    """Which top-level window is at screen (x, y), and where inside it."""
    if not SUPPORTED:
        return None
    hwnd = WindowFromPoint(wintypes.POINT(x, y))
    if not hwnd:
        return None
    top = GetAncestor(hwnd, GA_ROOT) or hwnd
    pt = wintypes.POINT(x, y)
    ScreenToClient(top, ctypes.byref(pt))
    return WindowSpot(_text(GetWindowTextW, top), _text(GetClassNameW, top), pt.x, pt.y)


def find_window(title: str, class_name: str):
    """Best visible top-level match: same title and class, else same title, else same class."""
    exact, by_title, by_class = [], [], []

    @WNDENUMPROC
    def visit(hwnd, _):
        if IsWindowVisible(hwnd):
            t, c = _text(GetWindowTextW, hwnd), _text(GetClassNameW, hwnd)
            if t == title and c == class_name:
                exact.append(hwnd)
            elif t == title and title:
                by_title.append(hwnd)
            elif c == class_name:
                by_class.append(hwnd)
        return True

    EnumWindows(visit, 0)
    for found in (exact, by_title, by_class):
        if found:
            return found[0]
    return None


def _deepest_child(hwnd, sx: int, sy: int):
    """Descend to the innermost child window under screen point (sx, sy)."""
    flags = CWP_SKIPINVISIBLE | CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT
    for _ in range(32):
        pt = wintypes.POINT(sx, sy)
        ScreenToClient(hwnd, ctypes.byref(pt))
        child = ChildWindowFromPointEx(hwnd, pt, flags)
        if not child or child == hwnd:
            break
        hwnd = child
    return hwnd


def post_click(hwnd, sx: int, sy: int, button: str, clicks: int) -> None:
    """Send a click at screen point (sx, sy) to hwnd (or its child there)."""
    target = _deepest_child(hwnd, sx, sy)
    pt = wintypes.POINT(sx, sy)
    ScreenToClient(target, ctypes.byref(pt))
    lparam = ((pt.y & 0xFFFF) << 16) | (pt.x & 0xFFFF)
    down, up, dbl, flag = MESSAGES[button]
    PostMessageW(target, WM_MOUSEMOVE, 0, lparam)
    PostMessageW(target, down, flag, lparam)
    PostMessageW(target, up, 0, lparam)
    if clicks == 2:
        PostMessageW(target, dbl, flag, lparam)
        PostMessageW(target, up, 0, lparam)


def background_click(point) -> None:
    """Click a ClickPoint in its saved window without moving the cursor."""
    if not SUPPORTED:
        raise RuntimeError("background clicking only works on Windows")
    if not point.window_class:
        raise RuntimeError(f"re-pick point {point.name} to use background clicking")
    hwnd = find_window(point.window_title, point.window_class)
    if not hwnd:
        raise RuntimeError(f"can't find the window '{point.window_title}' for point {point.name}")
    if IsIconic(hwnd):
        raise RuntimeError(f"the window for point {point.name} is minimized; restore it (it can stay behind others)")
    origin = wintypes.POINT(0, 0)
    ClientToScreen(hwnd, ctypes.byref(origin))
    post_click(hwnd, origin.x + point.rel_x, origin.y + point.rel_y, point.button, point.clicks)
