"""Real background-click test; runs on the Windows CI build.

Uses a plain Win32 window (not Tk: Tk checks the physical button state, so it
ignores posted clicks) with a child window, and records the mouse messages
each receives.
"""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_background_click_reaches_window_without_moving_cursor():
    import ctypes
    from ctypes import wintypes

    from autoclicker import winclick
    from autoclicker.model import ClickPoint

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
        ]

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = LRESULT
    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    received = []

    @WNDPROC
    def wndproc(hwnd, msg, wparam, lparam):
        if 0x0201 <= msg <= 0x0209:
            received.append((hwnd, msg, lparam & 0xFFFF, (lparam >> 16) & 0xFFFF))
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    hinst = kernel32.GetModuleHandleW(None)
    wc = WNDCLASSW(lpfnWndProc=wndproc, hInstance=hinst, lpszClassName="AutoclickerTestWnd")
    assert user32.RegisterClassW(ctypes.byref(wc))

    WS_OVERLAPPEDWINDOW, WS_VISIBLE, WS_CHILD = 0x00CF0000, 0x10000000, 0x40000000
    HWND_TOPMOST, SWP_NOSIZE = wintypes.HWND(-1), 0x0001
    top = user32.CreateWindowExW(0, "AutoclickerTestWnd", "autoclicker-test-target",
                                 WS_OVERLAPPEDWINDOW | WS_VISIBLE, 200, 200, 400, 300, None, None, hinst, None)
    child = user32.CreateWindowExW(0, "AutoclickerTestWnd", "", WS_CHILD | WS_VISIBLE,
                                   40, 40, 200, 120, top, None, hinst, None)
    assert top and child
    user32.SetWindowPos(top, HWND_TOPMOST, 200, 200, 0, 0, SWP_NOSIZE)

    def pump():
        msg = wintypes.MSG()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    try:
        pump()
        user32.SetCursorPos(5, 5)

        # Pick a spot 30,25 inside the child window, like the overlay would.
        origin = wintypes.POINT(0, 0)
        user32.ClientToScreen(child, ctypes.byref(origin))
        spot = winclick.window_at(origin.x + 30, origin.y + 25)
        assert spot is not None and spot.title == "autoclicker-test-target"

        # Window moves after picking: the saved spot must follow it.
        user32.SetWindowPos(top, HWND_TOPMOST, 260, 240, 0, 0, SWP_NOSIZE)
        pump()

        for button, count in (("left", 1), ("right", 1), ("left", 2)):
            winclick.background_click(ClickPoint(
                "A", 0, 0, button=button, clicks=count,
                window_title=spot.title, window_class=spot.class_name,
                rel_x=spot.rel_x, rel_y=spot.rel_y,
            ))
        pump()

        pos = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pos))
    finally:
        user32.DestroyWindow(top)

    assert [r[1:] for r in received] == [
        (0x0201, 30, 25), (0x0202, 30, 25),  # left
        (0x0204, 30, 25), (0x0205, 30, 25),  # right
        (0x0201, 30, 25), (0x0202, 30, 25), (0x0203, 30, 25), (0x0202, 30, 25),  # double
    ]
    assert all(r[0] == child for r in received)
    assert (pos.x, pos.y) == (5, 5)
