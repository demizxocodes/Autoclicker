"""Real background-click test; runs on the Windows CI build."""

import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_background_click_reaches_window_without_moving_cursor():
    import ctypes
    import tkinter as tk
    from ctypes import wintypes

    from autoclicker import winclick
    from autoclicker.model import ClickPoint

    ctypes.windll.user32.SetCursorPos(5, 5)
    root = tk.Tk()
    root.title("autoclicker-test-target")
    root.geometry("300x200+200+200")
    root.attributes("-topmost", True)
    target = tk.Frame(root, width=200, height=120, bg="white")
    target.place(x=40, y=40)
    clicks = []
    target.bind("<Button-1>", lambda e: clicks.append(("left", e.x, e.y)))
    target.bind("<Double-Button-1>", lambda e: clicks.append(("double", e.x, e.y)))
    target.bind("<Button-3>", lambda e: clicks.append(("right", e.x, e.y)))
    for _ in range(20):
        root.update()
        time.sleep(0.02)

    sx, sy = target.winfo_rootx() + 30, target.winfo_rooty() + 25
    spot = winclick.window_at(sx, sy)
    assert spot is not None and spot.title == "autoclicker-test-target"

    def click(button, count):
        point = ClickPoint("A", sx, sy, button=button, clicks=count,
                           window_title=spot.title, window_class=spot.class_name,
                           rel_x=spot.rel_x, rel_y=spot.rel_y)
        winclick.background_click(point)
        for _ in range(20):
            root.update()
            time.sleep(0.01)

    # Window moved after picking: the saved spot must follow it.
    root.geometry("+260+240")
    for _ in range(20):
        root.update()
        time.sleep(0.02)
    click("left", 1)
    click("right", 1)
    click("left", 2)

    pos = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pos))
    root.destroy()

    assert ("left", 30, 25) in clicks
    assert ("right", 30, 25) in clicks
    assert ("double", 30, 25) in clicks
    assert (pos.x, pos.y) == (5, 5)
