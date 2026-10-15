"""Full-screen see-through overlay: click anywhere to capture that screen position."""

from __future__ import annotations

import sys
import tkinter as tk
from typing import Callable


def virtual_screen(root: tk.Misc) -> tuple[int, int, int, int]:
    """(x, y, width, height) covering every monitor."""
    if sys.platform == "win32":
        import ctypes

        metrics = ctypes.windll.user32.GetSystemMetrics
        # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN
        return metrics(76), metrics(77), metrics(78), metrics(79)
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def pick_location(
    root: tk.Tk, point_name: str, callback: Callable[[tuple[int, int] | None], None]
) -> None:
    """Hide the main window, let the user click a spot, then call callback((x, y)).

    callback(None) means the user cancelled with Esc or right-click. The callback
    runs while the screen is uncovered, before the main window reappears.
    """
    root.withdraw()
    # Give the main window a moment to vanish before covering the screen.
    root.after(200, lambda: _show_overlay(root, point_name, callback))


def _show_overlay(root, point_name, callback):
    vx, vy, vw, vh = virtual_screen(root)

    overlay = tk.Toplevel(root)
    overlay.overrideredirect(True)
    overlay.attributes("-topmost", True)
    # Not fully transparent: Windows passes clicks through 0-alpha windows.
    overlay.attributes("-alpha", 0.3)
    overlay.configure(bg="black", cursor="crosshair")
    overlay.geometry(f"{vw}x{vh}+{vx}+{vy}")

    tip = tk.Toplevel(root)
    tip.overrideredirect(True)
    tip.attributes("-topmost", True)
    tip.configure(bg="#1f6feb", cursor="crosshair")
    text = tk.StringVar(
        value=f"Click where point {point_name} should click   ·   Esc or right-click to cancel"
    )
    tk.Label(
        tip, textvariable=text, bg="#1f6feb", fg="white",
        font=("Segoe UI", 13, "bold"), padx=18, pady=10,
    ).pack()
    tip.update_idletasks()
    tip_x = (root.winfo_screenwidth() - tip.winfo_reqwidth()) // 2
    tip.geometry(f"+{tip_x}+30")

    done = False

    def finish(result):
        nonlocal done
        if done:
            return
        done = True
        overlay.destroy()
        tip.destroy()
        # Callback runs before the main window comes back, so it can still
        # see which app window is under the picked spot.
        root.update()
        try:
            callback(result)
        finally:
            root.deiconify()
            root.lift()

    def on_motion(event):
        text.set(
            f"Point {point_name}:  X {event.x_root}   Y {event.y_root}"
            "   ·   click to set, Esc or right-click to cancel"
        )

    for win in (overlay, tip):
        win.bind("<Button-1>", lambda e: finish((e.x_root, e.y_root)))
        win.bind("<Button-3>", lambda e: finish(None))
        win.bind("<Escape>", lambda e: finish(None))
        win.bind("<Motion>", on_motion)

    overlay.lift()
    tip.lift()
    overlay.focus_force()
